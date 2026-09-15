/* Optional durable backing for the NP560 NAND medium, not a guest ABI. */
#ifndef HW_DMCU_NP560_NAND_JOURNAL_H
#define HW_DMCU_NP560_NAND_JOURNAL_H

typedef struct NP560NANDJournal NP560NANDJournal;

enum {
    NP560_JOURNAL_PROGRAM = 1,
    NP560_JOURNAL_OOB = 2,
    NP560_JOURNAL_ERASE = 3,
};

NP560NANDJournal *np560_nand_journal_open(const char *path,
    uint8_t *data, uint8_t *oob, uint32_t page_data, uint32_t page_oob,
    uint32_t pages, uint32_t block_pages, Error **errp);
bool np560_nand_journal_append(NP560NANDJournal *s, unsigned operation,
    uint32_t page, uint32_t column, const uint8_t *bytes, uint32_t length,
    Error **errp);
char *np560_nand_journal_state(const NP560NANDJournal *s);
char *np560_nand_journal_maintenance(const NP560NANDJournal *s);
bool np560_nand_journal_compact(NP560NANDJournal *s, Error **errp);
bool np560_nand_journal_protects(const NP560NANDJournal *s, const char *path);
void np560_nand_journal_close(NP560NANDJournal *s);

#endif
