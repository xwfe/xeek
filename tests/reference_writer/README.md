# 固定 Rust 库的合成参考写入器

此目录使用 keepass = 0.15.3，验证“读取已有公开合成 KDBX 4.1 → 改一个 UserName → 保存为新文件”。它是 K002/K069 的参考夹具工具，尚有明确语义差异；不是生产 writer 或 K003/K009 选型结论。完整版本、许可、参数、失败与实测见 [K002_LIBRARIES](../../adr/evidence/K002_LIBRARIES.md)。

## 依赖和构建

Cargo.toml 固定 keepass 精确版本、关闭默认 features，仅开启 save_kdbx4。Cargo.lock 固定传递解析和 registry 校验和。上游 [固定提交](https://github.com/sseemayer/keepass-rs/tree/15afd4da3d2f305069c7940795af1de9645fd81c) 为 MIT，保存能力仍属实验性且仅写 KDBX 4.1。替换库只影响这个独立 helper；不将其类型暴露给 Flutter、Web 或领域代码。

本机复用已有 Rust/Cargo 1.98.0、Python 3.12.12 和 KeePassXC CLI 2.7.12。首次在获得依赖下载授权后，使用现有 Cargo 配置填充固定版本缓存：

~~~sh
cargo build --locked --release --manifest-path tests/reference_writer/Cargo.toml --target-dir tests/reference_writer/target
~~~

缓存齐备后可离线重编译：

~~~sh
cargo build --locked --offline --release --manifest-path tests/reference_writer/Cargo.toml --target-dir tests/reference_writer/target
cargo fmt --manifest-path tests/reference_writer/Cargo.toml -- --check
~~~

Python oracle 的两个新 Argon2 包按 [测试依赖说明](../kdbx_oracle/README.md) 安装在项目内。缺失依赖会显式失败，不把 Argon2d 跳过当通过。生成器需要现有 KeePassXC 做交叉读取，不负责安装工具链。

## 生成与验证

仓库根目录执行：

~~~sh
python3 -B tests/reference_writer/generate.py
python3 -B tests/run_python_tests.py --suite oracle --pattern test_reference_writer.py -v
~~~

已有 rust_writer_manifest.json 时，生成器只核对源码版本、12 个案例参数、原输入与产物哈希，然后无操作退出。它不重新加密或构建，也不接受未登记文件。首次生成会先执行固定 target-dir 的 locked/offline build，阻止把旧二进制产物记成新源码结果。

输入固定为 m41-passkey-edit1.kdbx 与 v41-vault-edit1.kdbx；每个输入分别生成 AES-KDF/Argon2d/Argon2id × AES/ChaCha20 六组输出。AES-KDF 为 1000000 轮，Argon2为 v19、8 MiB、2 次、并行 1，仅用于算法夹具，不是生产 KDF 建议。公开合成密码、编辑目标和文件哈希保存在 [清单](../fixtures/kdbx/rust_writer_manifest.json)。

helper 参数顺序为 INPUT OUTPUT UUID NEW_USERNAME KDF CIPHER；密码从单行标准输入读取，不进入 argv。它先在内存完成加密，再以 create_new 创建新目标；Unix 新文件权限为 0600。拒绝覆盖源文件或任何已有目标，一个 edit_tracking 只产生一份编辑前历史。只打印计数或稳定错误码。

工具仅供已知合成输入使用。64 MiB 输入文件上限不代表已限制 Rust 库读取恶意 KDF、解压或 XML 的全部资源；oracle 的资源预算也不会自动应用到 Rust 库内部。

## 当前判定

12 份输出均能由独立 oracle 与 KeePassXC 重新读取，当前字段/保护位、旧历史快照和全部附件内容保留。同 RP 三把 P-256 凭据的身份、密钥和父关联保持配对。两类输入分别保留 39/36 个当前条目、9 个分组、6 份共 3300 字节附件；总历史均从 4 增为 5。

每份保留 9 条原始语义差异。除了目标 UserName、修改时间和新历史插到开头，还发现根分组子节点重排和两个默认 IconID 移除。因此全部样本明确 lossless_roundtrip=false。不会扩大 ignore 列表、改写旧源或将这些差异当成生产无损通过。

附件原始排列另存 attachment_order_changes：固定产物中 9 份有变化，共 12 处。比较仍严格检查名称、内容、保护位和重复次数。KeePassXC 的 4.x XML 导出缺少完整附件池，所以该交叉读只验证字段/历史，附件由独立解码器相对原输入逐字比较。

15 项回归覆盖固定版本/来源、全部算法组合、历史前插、同 RP 身份、剩余差异、错误密码/密文损坏、实际保存、已有目标拒绝、错误参数/格式、内容保留负例、无操作重跑及清单失败清理。缺少 helper 或 CLI 的环境会明确显示相应 live/交叉读测试跳过，不算完整验收；本机分项运行无跳过。

## 追溯与失败处理

清单保留原生成源码哈希、生成二进制哈希、构建/生成会话、原输入哈希和每份原始差异。生成后补上离线构建守卫和案例校验时，只更新当前验证 provenance；generation_provenance 保留原始哈希，12 份 KDBX 没有重写。

后续 4.x 负载批次仅更新当前 reader 验证哈希并追加 verification_revisions，generation_provenance 与 12 份 KDBX 继续保留。当前相对原生成只有 generator 和 reader 两项源码变化；本次修复与复核见 [K002_RESOURCES](../../adr/evidence/K002_RESOURCES.md)。

首次生成先在受限临时目录完成全部 12 份保存、解码和交叉读取，再排他发布。普通异常仅清理本次新建文件。强杀、磁盘故障仍可能留下锁、部分清单或未登记文件，下次拒绝覆盖；需核对原进程、来源与哈希后处理，不自动认领或删除。这里没有生产事务保存、并发控制或崩溃恢复承诺。

