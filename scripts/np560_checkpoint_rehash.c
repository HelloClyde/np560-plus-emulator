/* Recompute the two FNV-1a payload hashes in an NP560 NAND checkpoint. */

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define HEADER_SIZE 64u

static uint32_t load_le32(const unsigned char *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
           (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static uint64_t load_le64(const unsigned char *p)
{
    return (uint64_t)load_le32(p) | (uint64_t)load_le32(p + 4) << 32;
}

static void store_le32(unsigned char *p, uint32_t value)
{
    p[0] = value;
    p[1] = value >> 8;
    p[2] = value >> 16;
    p[3] = value >> 24;
}

static uint32_t hash_region(FILE *file, uint64_t length)
{
    unsigned char buffer[1u << 20];
    uint32_t hash = 2166136261u;

    while (length) {
        size_t wanted = length < sizeof(buffer) ? (size_t)length : sizeof(buffer);
        size_t got = fread(buffer, 1, wanted, file);
        size_t i;

        if (got != wanted) {
            fprintf(stderr, "checkpoint read failed: %s\n",
                    ferror(file) ? strerror(errno) : "unexpected EOF");
            exit(EXIT_FAILURE);
        }
        for (i = 0; i < got; i++) {
            hash = (hash ^ buffer[i]) * 16777619u;
        }
        length -= got;
    }
    return hash;
}

int main(int argc, char **argv)
{
    static const unsigned char magic[8] = {
        'N', 'P', '5', '6', '0', 'N', '1', 0
    };
    unsigned char header[HEADER_SIZE];
    uint64_t data_size;
    uint64_t oob_size;
    uint32_t data_hash;
    uint32_t oob_hash;
    FILE *file;

    if (argc != 2) {
        fprintf(stderr, "usage: %s CHECKPOINT\n", argv[0]);
        return EXIT_FAILURE;
    }
    file = fopen(argv[1], "r+b");
    if (!file) {
        fprintf(stderr, "cannot open %s: %s\n", argv[1], strerror(errno));
        return EXIT_FAILURE;
    }
    if (fread(header, 1, sizeof(header), file) != sizeof(header) ||
        memcmp(header, magic, sizeof(magic)) ||
        load_le32(header + 12) != HEADER_SIZE) {
        fprintf(stderr, "%s is not a supported NP560 checkpoint\n", argv[1]);
        fclose(file);
        return EXIT_FAILURE;
    }
    data_size = load_le64(header + 32);
    oob_size = load_le64(header + 40);
    data_hash = hash_region(file, data_size);
    oob_hash = hash_region(file, oob_size);
    store_le32(header + 48, data_hash);
    store_le32(header + 52, oob_hash);
    if (fseek(file, 0, SEEK_SET) ||
        fwrite(header, 1, sizeof(header), file) != sizeof(header) ||
        fclose(file)) {
        fprintf(stderr, "checkpoint header update failed: %s\n", strerror(errno));
        return EXIT_FAILURE;
    }
    printf("DATA_HASH=%08x OOB_HASH=%08x\n", data_hash, oob_hash);
    return EXIT_SUCCESS;
}
