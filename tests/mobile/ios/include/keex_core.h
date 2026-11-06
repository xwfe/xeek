// K004：Rust 核心的 C ABI，Swift 和未来的凭据扩展都走这里。约定见 tests/wasm_core/src/native.rs。
#ifndef KEEX_CORE_H
#define KEEX_CORE_H
#include <stddef.h>
#include <stdint.h>

typedef struct KeexVault KeexVault;

const char *keex_last_error(void);
int32_t keex_vault_open(const uint8_t *data, size_t length, const char *password, uint64_t budget, KeexVault **out);
char *keex_vault_summary(const KeexVault *vault);
int32_t keex_vault_set_username(KeexVault *vault, const char *entry, const char *username);
int32_t keex_vault_set_kdf(KeexVault *vault, const char *name, uint32_t memory_mib, uint32_t iterations, uint32_t parallelism);
int32_t keex_vault_save(const KeexVault *vault, const char *password, uint8_t **out, size_t *out_length);
int32_t keex_test_panic(void);
void keex_bytes_free(uint8_t *data, size_t length);
void keex_string_free(char *value);
void keex_vault_free(KeexVault *vault);
#endif
