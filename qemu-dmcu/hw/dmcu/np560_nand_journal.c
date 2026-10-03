/*
 * Immutable NAND seed + exclusively locked, durable command journal.
 * Commit precedes the corresponding in-memory mutation and ready status.
 * This preserves completed commands across QEMU process failure; it does
 * not model analog power loss partway through a physical NAND operation.
 */
#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qemu/bswap.h"
#include "qemu/crc32c.h"
#include "qemu/error-report.h"
#include "np560_nand_journal.h"

#define HEADER_SIZE 64u
#define RECORD_SIZE 32u
#define COMPACT_GROWTH (16u * 1024u * 1024u)

struct NP560NANDJournal {
    int fd, lock_fd;
    bool failed;
    char *path;
    uint8_t header[HEADER_SIZE];
    uint8_t *data, *oob, *base_hashes, *tracked;
    uint8_t *erased_block, erased_hash[32];
    uint32_t page_data, page_oob, pages, block_pages;
    uint64_t sequence, replayed, torn_bytes;
    uint64_t noop_erases;
    uint64_t bytes, compact_at, compactions, reclaimed;
    char *maintenance_error;
};

bool np560_nand_journal_protects(const NP560NANDJournal *s, const char *path)
{
    struct stat target, owned;

    if (!s || stat(path, &target) < 0) {
        return false;
    }
    return (s->fd >= 0 && fstat(s->fd, &owned) == 0 &&
            target.st_dev == owned.st_dev && target.st_ino == owned.st_ino) ||
           (s->lock_fd >= 0 && fstat(s->lock_fd, &owned) == 0 &&
            target.st_dev == owned.st_dev && target.st_ino == owned.st_ino);
}

#ifndef _WIN32
/* Caller holds the stable sidecar lock. Closing/reopening journal handles
 * around rename avoids DrvFS's inaccessible live-renamed-file behavior. */
static bool reopen_journal(NP560NANDJournal *s)
{
    struct stat owned, current;
    int lock_result;

    s->fd = qemu_open(s->path, O_RDWR | O_BINARY, NULL);
    if (s->fd < 0) {
        return false;
    }
    lock_result = qemu_lock_fd(s->fd, 0, 0, true);
    if (lock_result < 0) {
        errno = -lock_result;
        return false;
    }
    if (fstat(s->fd, &owned) < 0 || lstat(s->path, &current) < 0 ||
        owned.st_ino != current.st_ino || owned.st_dev != current.st_dev ||
        owned.st_size != s->bytes || lseek(s->fd, s->bytes, SEEK_SET) < 0) {
        return false;
    }
    return true;
}
#endif

static bool block_is_erased(const NP560NANDJournal *s, uint32_t block)
{
    uint32_t page = block * s->block_pages;
    size_t data_length = (size_t)s->block_pages * s->page_data;
    size_t oob_length = (size_t)s->block_pages * s->page_oob;

    return !memcmp(s->data + (size_t)page * s->page_data,
                   s->erased_block, data_length) &&
           !memcmp(s->oob + (size_t)page * s->page_oob,
                   s->erased_block + data_length, oob_length);
}

static void block_hash(NP560NANDJournal *s, uint32_t block, uint8_t *digest)
{
    uint32_t page = block * s->block_pages;
    GChecksum *checksum;
    gsize length = 32;

    /* Native boot may erase thousands of already-erased blocks. Exact
     * memcmp + one cached SHA-256 avoids rehashing 512 MiB of identical FF
     * data during replay, without weakening equality to a short checksum. */
    if (block_is_erased(s, block)) {
        memcpy(digest, s->erased_hash, 32);
        return;
    }
    checksum = g_checksum_new(G_CHECKSUM_SHA256);
    g_checksum_update(checksum, s->data + (size_t)page * s->page_data,
                      (size_t)s->block_pages * s->page_data);
    g_checksum_update(checksum, s->oob + (size_t)page * s->page_oob,
                      (size_t)s->block_pages * s->page_oob);
    g_checksum_get_digest(checksum, digest, &length);
    g_checksum_free(checksum);
}

/* Capture the immutable seed digest before the FIRST mutation of a block,
 * including during replay. Only 33 bytes per block, not another NAND copy.
 * The OOB command can cross a page and therefore a block boundary. */
static void track_blocks(NP560NANDJournal *s, unsigned op, uint32_t page,
                         uint32_t column, uint32_t length)
{
    uint32_t last = page, block;

    if (op == NP560_JOURNAL_OOB && length) {
        last += (column - s->page_data + length - 1) / s->page_oob;
    }
    for (block = page / s->block_pages;
         block <= last / s->block_pages; block++) {
        if (!s->tracked[block]) {
            block_hash(s, block, s->base_hashes + (size_t)block * 32);
            s->tracked[block] = 1;
        }
    }
}

static bool write_record(int fd, uint64_t sequence, unsigned operation,
                         uint32_t page, uint32_t column,
                         const uint8_t *bytes, uint32_t length)
{
    uint8_t record[RECORD_SIZE] = { 'N', 'J', 'R', '1' };
    uint32_t crc;

    stl_le_p(record + 4, operation);
    stq_le_p(record + 8, sequence);
    stl_le_p(record + 16, page);
    stl_le_p(record + 20, column);
    stl_le_p(record + 24, length);
    crc = crc32c(0xffffffffu, record, 28);
    if (length) {
        crc = crc32c(crc ^ 0xffffffffu, bytes, length);
    }
    stl_le_p(record + 28, crc);
    return qemu_write_full(fd, record, RECORD_SIZE) == RECORD_SIZE &&
           (!length || qemu_write_full(fd, bytes, length) == length);
}

/* Encode the final page relative to an erased block, retaining both planes.
 * Leading/trailing erased bytes need not be stored. Interior FF bytes are
 * retained, rather than assuming that every page contains ordinary data. */
static uint32_t page_span(NP560NANDJournal *s, uint32_t page, uint8_t *payload,
                          uint32_t *column)
{
    uint32_t end = s->page_data + s->page_oob;

    memcpy(payload, s->data + (size_t)page * s->page_data, s->page_data);
    memcpy(payload + s->page_data, s->oob + (size_t)page * s->page_oob,
           s->page_oob);
    *column = 0;
    while (*column < end && payload[*column] == 0xff) {
        (*column)++;
    }
    while (end > *column && payload[end - 1] == 0xff) {
        end--;
    }
    return end - *column;
}

bool np560_nand_journal_compact(NP560NANDJournal *s, Error **errp)
{
#ifdef _WIN32
    error_setg(errp, "NP560 NAND journal compaction requires POSIX");
    return false;
#else
    g_autofree uint8_t *changed = NULL;
    g_autofree uint8_t *payload = NULL;
    g_autofree char *temporary = NULL;
    g_autofree char *parent = NULL;
    uint64_t size = HEADER_SIZE, sequence = 0;
    uint32_t block, page, column, length;
    struct stat owned, current;
    int fd = -1, dirfd = -1, saved_errno;
    bool published = false, temporary_created = false;

    if (!s || s->failed) {
        error_setg(errp, "NP560 NAND journal is disabled or failed");
        return false;
    }
    /* Never replace an unrelated path or split an aliased medium into two
     * silently diverging files. Symlinks were resolved once at open. */
    if (fstat(s->fd, &owned) < 0 || lstat(s->path, &current) < 0 ||
        !S_ISREG(current.st_mode) || owned.st_dev != current.st_dev ||
        owned.st_ino != current.st_ino || owned.st_size != s->bytes) {
        s->failed = true;
        error_setg(errp, "NP560 NAND journal path or size changed");
        return false;
    }
    if (owned.st_nlink != 1) {
        error_setg(errp, "NP560 NAND journal has hard links");
        return false;
    }
    changed = g_malloc0(s->pages / s->block_pages);
    payload = g_malloc(s->page_data + s->page_oob);
    for (block = 0; block < s->pages / s->block_pages; block++) {
        uint8_t digest[32];

        if (!s->tracked[block]) {
            continue;
        }
        block_hash(s, block, digest);
        if (!memcmp(digest, s->base_hashes + (size_t)block * 32, 32)) {
            continue;
        }
        changed[block] = 1;
        size += RECORD_SIZE; /* erase, including blocks now entirely FF */
        for (page = block * s->block_pages;
             page < (block + 1) * s->block_pages; page++) {
            length = page_span(s, page, payload, &column);
            if (length) {
                size += RECORD_SIZE + length;
            }
        }
    }
    /* Do not increase disk use when the history is already the smaller
     * representation. Retry only after substantial additional growth. */
    s->compact_at = s->bytes + MAX(s->bytes, COMPACT_GROWTH);
    if (size >= s->bytes) {
        return true;
    }
    parent = g_path_get_dirname(s->path);
    dirfd = qemu_open(parent, O_RDONLY | O_DIRECTORY, errp);
    if (dirfd < 0) {
        return false;
    }
    /* Fail before publication if this filesystem cannot sync directories. */
    if (fsync(dirfd) < 0) {
        goto io_error;
    }
    temporary = g_strdup_printf("%s.compact.XXXXXX", s->path);
    fd = g_mkstemp_full(temporary, O_RDWR | O_CLOEXEC, 0600);
    if (fd < 0) {
        goto io_error;
    }
    temporary_created = true;
    if (qemu_write_full(fd, s->header, HEADER_SIZE) != HEADER_SIZE) {
        goto io_error;
    }
    for (block = 0; block < s->pages / s->block_pages; block++) {
        if (!changed[block]) {
            continue;
        }
        page = block * s->block_pages;
        if (!write_record(fd, ++sequence, NP560_JOURNAL_ERASE,
                          page, 0, NULL, 0)) {
            goto io_error;
        }
        for (; page < (block + 1) * s->block_pages; page++) {
            length = page_span(s, page, payload, &column);
            if (length && !write_record(fd, ++sequence,
                    column < s->page_data ? NP560_JOURNAL_PROGRAM :
                                           NP560_JOURNAL_OOB,
                    page, column, payload + column, length)) {
                goto io_error;
            }
        }
    }
    if (qemu_fdatasync(fd) < 0) {
        goto io_error;
    }
    qemu_close(fd);
    fd = -1;
    if (lstat(s->path, &current) < 0 || owned.st_dev != current.st_dev ||
        owned.st_ino != current.st_ino || current.st_nlink != 1) {
        errno = ESTALE;
        goto io_error;
    }
    qemu_close(s->fd);
    s->fd = -1;
    if (rename(temporary, s->path) < 0) {
        goto io_error;
    }
    /* The stable sidecar remains locked throughout close/rename/reopen.
     * Never append to the unlinked old inode on a post-rename failure. */
    published = true;
    s->reclaimed += s->bytes - size;
    s->bytes = size;
    s->sequence = sequence;
    s->compactions++;
    s->compact_at = size + MAX(size, COMPACT_GROWTH);
    if (fsync(dirfd) < 0 || !reopen_journal(s)) {
        s->failed = true;
        goto io_error;
    }
    qemu_close(dirfd);
    g_clear_pointer(&s->maintenance_error, g_free);
    return true;

io_error:
    saved_errno = errno ? errno : EIO;
    if (fd >= 0) {
        qemu_close(fd);
    }
    /* Only this invocation's exclusively created temporary is removed.
     * A SIGKILL may leave it behind; startup never treats it as a log. */
    if (temporary_created && !published) {
        unlink(temporary);
    }
    if (!published && s->fd < 0 && !reopen_journal(s)) {
        s->failed = true;
    }
    if (dirfd >= 0) {
        qemu_close(dirfd);
    }
    error_setg_errno(errp, saved_errno, "NP560 NAND journal compaction failed");
    return false;
#endif
}

char *np560_nand_journal_maintenance(const NP560NANDJournal *s)
{
    if (!s) {
        return g_strdup("disabled");
    }
    return g_strdup_printf("BYTES=%" PRIu64 " COMPACTIONS=%" PRIu64
                           " RECLAIMED=%" PRIu64 " NEXT=%" PRIu64 " ERROR=%s",
                           s->bytes, s->compactions, s->reclaimed, s->compact_at,
                           s->maintenance_error ? s->maintenance_error : "none");
}

static bool valid_record(NP560NANDJournal *s, unsigned op, uint32_t page,
                         uint32_t column, uint32_t length)
{
    uint64_t offset;

    if (page >= s->pages) {
        return false;
    }
    switch (op) {
    case NP560_JOURNAL_PROGRAM:
        return column < s->page_data &&
               length <= s->page_data + s->page_oob - column;
    case NP560_JOURNAL_OOB:
        if (column < s->page_data ||
            column - s->page_data > 4 * s->page_oob ||
            length > 4 * s->page_oob - (column - s->page_data)) {
            return false;
        }
        offset = (uint64_t)page * s->page_oob + column - s->page_data;
        return offset + length <= (uint64_t)s->pages * s->page_oob;
    case NP560_JOURNAL_ERASE:
        return page % s->block_pages == 0 && column == 0 && length == 0 &&
               s->pages - page >= s->block_pages;
    default:
        return false;
    }
}

static void replay_record(NP560NANDJournal *s, uint8_t *data, uint8_t *oob,
                          unsigned op, uint32_t page, uint32_t column,
                          const uint8_t *bytes, uint32_t length)
{
    uint32_t i;

    if (op == NP560_JOURNAL_ERASE) {
        memset(data + (size_t)page * s->page_data, 0xff,
               (size_t)s->block_pages * s->page_data);
        memset(oob + (size_t)page * s->page_oob, 0xff,
               (size_t)s->block_pages * s->page_oob);
    } else if (op == NP560_JOURNAL_OOB) {
        size_t offset = (size_t)page * s->page_oob + column - s->page_data;

        for (i = 0; i < length; i++) {
            oob[offset + i] &= bytes[i];
        }
    } else {
        for (i = 0; i < length; i++) {
            uint32_t c = column + i;

            if (c < s->page_data) {
                data[(size_t)page * s->page_data + c] &= bytes[i];
            } else {
                oob[(size_t)page * s->page_oob + c - s->page_data] &= bytes[i];
            }
        }
    }
}

typedef struct NP560JournalReader {
    int fd;
    size_t offset, length;
    uint8_t buffer[64 * 1024];
} NP560JournalReader;

/* Bounded read-ahead avoids two host filesystem round trips per record on
 * shared/WSL filesystems. The final seek uses the validated record boundary,
 * not the read-ahead fd position. No whole-journal allocation is needed.
 * Return short reads only at EOF; interruption is not a torn record. */
static ssize_t read_full(NP560JournalReader *reader, void *buffer, size_t length)
{
    size_t done = 0;

    while (done < length) {
        size_t count;

        if (reader->offset == reader->length) {
            ssize_t n = RETRY_ON_EINTR(read(reader->fd, reader->buffer,
                                          sizeof(reader->buffer)));
            if (n < 0) {
                return -1;
            }
            if (!n) {
                break;
            }
            reader->offset = 0;
            reader->length = n;
        }
        count = MIN(length - done, reader->length - reader->offset);
        memcpy((uint8_t *)buffer + done, reader->buffer + reader->offset,
               count);
        reader->offset += count;
        done += count;
    }
    return done;
}

NP560NANDJournal *np560_nand_journal_open(const char *path,
    uint8_t *data, uint8_t *oob, uint32_t page_data, uint32_t page_oob,
    uint32_t pages, uint32_t block_pages, Error **errp)
{
    NP560NANDJournal *s = g_new0(NP560NANDJournal, 1);
    uint8_t expected[HEADER_SIZE] = { 'N', 'P', '5', '6', '0', 'J', '1', 0 };
    uint8_t header[HEADER_SIZE], record[RECORD_SIZE];
    g_autofree uint8_t *payload = g_malloc(page_data + page_oob);
    g_autofree NP560JournalReader *reader = g_new0(NP560JournalReader, 1);
    gsize digest_size = 32;
    GChecksum *checksum;
    struct stat st;
    off_t end = HEADER_SIZE;
    ssize_t n;

    s->fd = -1;
    s->lock_fd = -1;
    s->page_data = page_data;
    s->page_oob = page_oob;
    s->pages = pages;
    s->block_pages = block_pages;
    s->data = data;
    s->oob = oob;
    s->tracked = g_malloc0(pages / block_pages);
    s->base_hashes = g_malloc0((size_t)(pages / block_pages) * 32);
    s->erased_block = g_malloc((size_t)block_pages * (page_data + page_oob));
    memset(s->erased_block, 0xff, (size_t)block_pages * (page_data + page_oob));
    s->compact_at = COMPACT_GROWTH;
    stl_le_p(expected + 8, 1);
    stl_le_p(expected + 12, page_data);
    stl_le_p(expected + 16, page_oob);
    stl_le_p(expected + 20, pages);
    stl_le_p(expected + 24, block_pages);
    checksum = g_checksum_new(G_CHECKSUM_SHA256);
    g_checksum_update(checksum, data, (size_t)pages * page_data);
    g_checksum_update(checksum, oob, (size_t)pages * page_oob);
    g_checksum_get_digest(checksum, expected + 32, &digest_size);
    g_checksum_free(checksum);
    memcpy(s->header, expected, HEADER_SIZE);
    checksum = g_checksum_new(G_CHECKSUM_SHA256);
    g_checksum_update(checksum, s->erased_block,
                      (size_t)block_pages * (page_data + page_oob));
    g_checksum_get_digest(checksum, s->erased_hash, &digest_size);
    g_checksum_free(checksum);

#ifdef _WIN32
    {
        g_autofree char *lock_path = NULL;
        struct stat lock_st;
        OVERLAPPED offset = { 0 };
        HANDLE handle;

        s->path = g_canonicalize_filename(path, NULL);
        lock_path = g_strdup_printf("%s.lock", s->path);
        s->lock_fd = qemu_create(lock_path, O_RDWR | O_BINARY, 0600, errp);
        if (s->lock_fd < 0) {
            goto fail;
        }
        if (fstat(s->lock_fd, &lock_st) < 0 || !S_ISREG(lock_st.st_mode) ||
            lock_st.st_size != 0) {
            error_setg(errp, "NP560 NAND sidecar lock must be an empty regular file");
            goto fail;
        }
        handle = (HANDLE)_get_osfhandle(s->lock_fd);
        if (handle == INVALID_HANDLE_VALUE || !LockFileEx(handle,
                LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY,
                0, 1, 0, &offset)) {
            error_setg(errp, "NP560 NAND journal is locked by another process");
            goto fail;
        }
        s->fd = qemu_create(s->path, O_RDWR | O_BINARY, 0600, errp);
        if (s->fd < 0) {
            goto fail;
        }
    }
#else
    {
        g_autofree char *lock_path = NULL;
        struct stat lock_st;

        s->path = realpath(path, NULL);
        if (!s->path && errno == ENOENT) {
            g_autofree char *parent = g_path_get_dirname(path);
            g_autofree char *base = g_path_get_basename(path);
            g_autofree char *resolved = realpath(parent, NULL);

            if (resolved) {
                s->path = g_build_filename(resolved, base, NULL);
            }
        }
        if (!s->path) {
            goto io_error;
        }
        lock_path = g_strdup_printf("%s.lock", s->path);
        s->lock_fd = qemu_create(lock_path, O_RDWR | O_BINARY | O_NOFOLLOW,
                                  0600, errp);
        if (s->lock_fd < 0) {
            goto fail;
        }
        if (fstat(s->lock_fd, &lock_st) < 0 || !S_ISREG(lock_st.st_mode) ||
            lock_st.st_size != 0 || lock_st.st_nlink != 1) {
            error_setg(errp, "NP560 NAND sidecar lock must be an empty regular file");
            goto fail;
        }
        if (qemu_lock_fd(s->lock_fd, 0, 0, true) < 0) {
            error_setg(errp, "NP560 NAND journal is locked by another process");
            goto fail;
        }
    }
    s->fd = qemu_create(s->path, O_RDWR | O_BINARY, 0600, errp);
    if (s->fd < 0) {
        goto fail;
    }
    if (qemu_lock_fd(s->fd, 0, 0, true) < 0) {
        error_setg(errp, "NP560 NAND journal is locked by another process");
        goto fail;
    }
#endif
    if (fstat(s->fd, &st) < 0 || !S_ISREG(st.st_mode)) {
        error_setg(errp, "NP560 NAND journal must be a regular file");
        goto fail;
    }
#ifndef _WIN32
    if (s->path) {
        struct stat current;

        /* An opener may have acquired an old fd just before compaction
         * renamed the log. Do not replay/append that retired inode. */
        if (stat(s->path, &current) < 0 || st.st_dev != current.st_dev ||
            st.st_ino != current.st_ino) {
            error_setg(errp, "NP560 NAND journal changed while opening; retry");
            goto fail;
        }
    } else {
        goto io_error;
    }
#endif
    if (st.st_size == 0) {
        if (qemu_write_full(s->fd, expected, HEADER_SIZE) != HEADER_SIZE ||
            qemu_fdatasync(s->fd) < 0) {
            goto io_error;
        }
        s->bytes = HEADER_SIZE;
        return s;
    }
    reader->fd = s->fd;
    n = read_full(reader, header, HEADER_SIZE);
    if (n < 0) {
        goto io_error;
    }
    if (n != HEADER_SIZE || memcmp(header, expected, HEADER_SIZE)) {
        error_setg(errp, "NP560 NAND journal header/base SHA-256 mismatch");
        goto fail;
    }
    while ((n = read_full(reader, record, RECORD_SIZE)) > 0) {
        unsigned op;
        uint32_t page, column, length, crc;

        if (n != RECORD_SIZE) {
            s->torn_bytes = n;
            break;
        }
        op = ldl_le_p(record + 4);
        page = ldl_le_p(record + 16);
        column = ldl_le_p(record + 20);
        length = ldl_le_p(record + 24);
        if (memcmp(record, "NJR1", 4) ||
            ldq_le_p(record + 8) != s->sequence + 1 ||
            !valid_record(s, op, page, column, length) ||
            length > page_data + page_oob) {
            error_setg(errp, "NP560 NAND journal invalid record at %" PRId64,
                       (int64_t)end);
            goto fail;
        }
        n = read_full(reader, payload, length);
        if (n < 0) {
            goto io_error;
        }
        if (n != length) {
            s->torn_bytes = RECORD_SIZE + n;
            break;
        }
        crc = crc32c(0xffffffffu, record, 28);
        if (length) {
            crc = crc32c(crc ^ 0xffffffffu, payload, length);
        }
        if (crc != ldl_le_p(record + 28)) {
            error_setg(errp, "NP560 NAND journal checksum error at %" PRId64,
                       (int64_t)end);
            goto fail;
        }
        track_blocks(s, op, page, column, length);
        replay_record(s, data, oob, op, page, column, payload, length);
        s->sequence++;
        end += RECORD_SIZE + length;
    }
    if (n < 0) {
        goto io_error;
    }
    s->replayed = s->sequence;
    if (s->torn_bytes) {
        /* Only incomplete EOF data is uncommitted. Never skip a complete
         * bad-checksum record, wrong base, sequence gap or invalid range. */
        if (ftruncate(s->fd, end) < 0 || qemu_fdatasync(s->fd) < 0) {
            goto io_error;
        }
        warn_report("NP560 NAND journal discarded %" PRIu64
                    " incomplete trailing bytes", s->torn_bytes);
    }
    if (lseek(s->fd, end, SEEK_SET) < 0) {
        goto io_error;
    }
    s->bytes = end;
    return s;

io_error:
    error_setg_errno(errp, errno ? errno : EIO, "NP560 NAND journal I/O failed");
fail:
    np560_nand_journal_close(s);
    return NULL;
}

bool np560_nand_journal_append(NP560NANDJournal *s, unsigned operation,
    uint32_t page, uint32_t column, const uint8_t *bytes, uint32_t length,
    Error **errp)
{
    if (!s) {
        return true;
    }
    if (s->failed) {
        error_setg(errp, "NP560 NAND journal is failed; restart after fixing I/O");
        return false;
    }
    if (!valid_record(s, operation, page, column, length)) {
        error_setg(errp, "NP560 NAND journal refused invalid mutation");
        return false;
    }
    /* Erasing an already-FF block changes neither NAND plane.  Preserve the
     * guest's successful erase command, but do not issue a durable journal
     * commit for a state transition that did not happen.  Native boot repeats
     * tens of thousands of these on a host-mounted journal; each old record
     * forced an fdatasync while guest virtual time was stopped.  Check both
     * planes exactly, including OOB, before eliding the record. */
    if (operation == NP560_JOURNAL_ERASE &&
        block_is_erased(s, page / s->block_pages)) {
        s->noop_erases++;
        return true;
    }
    if (s->bytes >= s->compact_at) {
        Error *local_err = NULL;

        if (!np560_nand_journal_compact(s, &local_err)) {
            g_free(s->maintenance_error);
            s->maintenance_error = g_strdup(error_get_pretty(local_err));
            s->compact_at = s->bytes + COMPACT_GROWTH;
            if (s->failed) {
                error_propagate(errp, local_err);
                return false;
            }
            warn_report_err(local_err); /* The old log is still intact. */
        }
    }
    track_blocks(s, operation, page, column, length);
    if (!write_record(s->fd, s->sequence + 1, operation, page, column,
                      bytes, length) ||
        qemu_fdatasync(s->fd) < 0) {
        s->failed = true; /* Do not append past an uncertain/torn commit. */
        error_setg_errno(errp, errno ? errno : EIO,
                         "NP560 NAND journal commit failed");
        return false;
    }
    s->sequence++;
    s->bytes += RECORD_SIZE + length;
    return true;
}

char *np560_nand_journal_state(const NP560NANDJournal *s)
{
    if (!s) {
        return g_strdup("disabled");
    }
    return g_strdup_printf("%s SEQUENCE=%" PRIu64 " REPLAYED=%" PRIu64
                           " TORN_BYTES=%" PRIu64 " NOOP_ERASES=%" PRIu64,
                           s->failed ? "failed" : "durable",
                           s->sequence, s->replayed, s->torn_bytes,
                           s->noop_erases);
}

void np560_nand_journal_close(NP560NANDJournal *s)
{
    if (s) {
        if (s->fd >= 0) {
            qemu_close(s->fd); /* Releases the exclusive lock. */
        }
        if (s->lock_fd >= 0) {
            /* Never unlink the stable lock file: waiters may already have
             * opened it. Removing it would allow two independent owners. */
            qemu_close(s->lock_fd);
        }
        g_free(s->path);
        g_free(s->tracked);
        g_free(s->base_hashes);
        g_free(s->erased_block);
        g_free(s->maintenance_error);
        g_free(s);
    }
}
