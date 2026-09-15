/* Test-only LD_PRELOAD fault points, scoped to one exact owned journal path.
 * Never linked into QEMU. Used by test_np560_nand_compaction.py. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int published;

int rename(const char *old_path, const char *new_path)
{
    int (*next_rename)(const char *, const char *) = dlsym(RTLD_NEXT, "rename");
    const char *target = getenv("NP560_FAULT_JOURNAL");
    const char *mode = getenv("NP560_FAULT_MODE");
    int selected = target && mode && !strcmp(new_path, target);
    int result;

    if (selected && !strcmp(mode, "before-rename")) {
        raise(SIGSTOP);
    }
    result = next_rename(old_path, new_path);
    if (!result && selected) {
        published = 1;
        if (!strcmp(mode, "after-rename")) {
            raise(SIGSTOP);
        }
    }
    return result;
}

int fsync(int fd)
{
    int (*next_fsync)(int) = dlsym(RTLD_NEXT, "fsync");
    const char *mode = getenv("NP560_FAULT_MODE");
    struct stat st;

    if (published && mode && !strcmp(mode, "directory-sync-error") &&
        !fstat(fd, &st) && S_ISDIR(st.st_mode)) {
        errno = EIO;
        return -1;
    }
    return next_fsync(fd);
}
