# K002 增量证据：固定 gzip 头部 OS 字节

日期：2026-11-22。K002 保持 REVIEW。本次只改测试生成器和复核规则，**没有改任何已登记样本的字节或摘要**，也不涉及产品 writer、生产门槛。本改动仍需独立复核。

## 问题

登记样本在 macOS 生成。zlib 在 gzip 头部偏移 9 写入构建平台的 OS 字节：Apple 的 zlib 写 19，Linux 的写 3。生成器在 Linux 上重建时只有这一个字节不同，压缩体和 trailer 逐字节相同，但整份文件的 SHA-256 因此对不上。归因过程见 [tests/README.md](../../tests/README.md) 的“Linux 全量回归”一节。

受影响的 Linux 全量回归项共 10 个：

| 生成器 | 回归项 |
| --- | --- |
| [mutate.py](../../tests/fixtures/kdbx/mutate.py) `gzip_deterministic` | 6 个 R31 变异样本的字节复现 |
| [source.py](../../tests/fixtures/kdbx/source.py) 附件池 | vault、matrix 两组源 XML 摘要 |
| [v4_payload.py](../../tests/fixtures/kdbx/v4_payload.py) `gzip_bytes` | 4.x 认证负载清单复现、生成器空跑 |

## 改动

1. 三个生成器压缩后把偏移 9 固定写成 19，即登记样本里已有的值。oracle 读取端不看这个字节。
2. `v4_payload.py` 复核已登记清单时不再要求 `runtime`（Python、zlib、cryptography 版本）与复核环境相同。`runtime` 保留为生成时的记录；全部 278 条记录的摘要、字节数和 4 份留存文件仍逐项比对。新增一项测试：只改 `runtime` 能通过，改任一记录摘要仍报 `manifest differs`。
3. 生成器文件的摘要登记在清单的 `provenance` 里，所以随之更新：
   - `vault_manifest.json`、`matrix_manifest.json`、`rust_writer_manifest.json`：`provenance` 中 `source.py` 的摘要换成当前值，并各加一条 `verification_revisions`（原摘要、新摘要、原因、本文件）。`matrix`、`rust_writer` 的 `generation_provenance` 保留原生成时的摘要不动。
   - `rust_writer_manifest.json` 还登记了 `vault_manifest.json`、`matrix_manifest.json` 的摘要，`dart_writer_manifest.json` 登记了这三份清单的摘要。它们按同样方式更新 `provenance`、追加 `verification_revisions`，`generation_provenance` 不动。
   - `v4_payload_manifest.json`：`provenance` 中 `v4_payload.py` 的摘要换成当前值。该清单由生成器整体比对，没有修订字段；原摘要见本次提交的 diff。
   - 三个守卫测试（`test_reference_writer`、`test_dart_candidate`、`test_matrix_generation`）原来写死了“生成后只有哪些文件变过”，现在把这批修订加进去，并核对每条修订的原摘要、新摘要与证据文件。
4. 秘密扫描的精确例外按文件摘要绑定，以上改过的已登记文件重新绑定摘要；没有增删规则或路径。

样本文件（`*.kdbx`）、各清单里的样本摘要、源 XML 摘要、`generation_provenance` 均未改。

## 验证

Linux x86_64，Python 3.12.12（zlib 1.3.1），KeePassXC CLI 2.7.12：

```sh
"$(uv python find 3.12.12)" -B tests/run_python_tests.py
```

```text
Ran 282 tests in 247.259s
FAILED (errors=1, skipped=4)
```

改动前同一环境为 `Ran 281 tests`、9 failures、2 errors。剩余 1 个 error 见下。

## 限制

- 未在 macOS 上复跑。按构造，macOS 上原本就写 19，固定后输出不变；实际结果待 macOS 环境确认。
- 剩余的 1 个 error 是 `test_candidate_minimal` 缺 Dart SDK。它属于 `kdbx.dart` 候选对照，不在 NSH + Rust 生产路线上，本机不安装。
- 以后若用各 `*generate.py` 扩充或重写清单，生成器不会自动带上 `verification_revisions`，需要人工保留。
