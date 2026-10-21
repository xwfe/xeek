# K002/K069 增量证据：成熟依赖、Argon2d 与 Rust 参考保存

日期：2026-10-19。按用户“可用一些流行、高效的库，来加快开发；继续”的明确授权，复用现有工具链并增加固定版本的测试依赖。K001/K002/K068 保持 REVIEW，K069 保持 DOING；K003–K067、K070–K089 仍为 TODO。这里完成合成参考实验，不替代 K003 双候选比较、K009 选型或人工独立门槛。

本页保留该批 198 项验收与当时的来源差异。后续 [K002_RESOURCES](K002_RESOURCES.md) 已补 4.x 不压缩/认证负载、gzip/base64 错误归一及内层歧义拒绝，当前入口增为 224 项；原文“仅有 generator 不同”为当时状态，现清单另有保留原生成哈希的 reader 验证修订。

## 本次交付

- 只读 oracle 接入 Argon2d v16/v19，保留已有 cryptography Argon2id 路径，增加派生前参数与 VariantDictionary 边界检查。
- 固定 keepass 0.15.3，新增 [Rust 参考 helper](../../tests/reference_writer/README.md)，只对已登记的公开合成 KDBX 4.1 输入修改一个 UserName 并保存到新文件。
- 两类输入 × 三种 KDF × 两种外层密码，共 12 份新样本、470330 字节，见 [rust_writer_manifest.json](../../tests/fixtures/kdbx/rust_writer_manifest.json)。原有 66 份 KDBX 字节保留；上游来源清单仅更新 oracle 结果并保留接入前状态。
- 新增 24 项 KDF/解析边界测试及 15 项参考产物/失败保护测试；原 9 项上游测试扩展到 Argon2d 正向读取。测试入口为 oracle 105 项、领域 93 项，共 198 项；最终统一执行以本批任务验收会话为准。

## 依赖、许可与替换边界

| 依赖 | 固定版本与许可 | 本轮使用及维护依据 | 替换边界 |
| --- | --- | --- | --- |
| cryptography | 46.0.4；Apache-2.0 OR BSD-3-Clause | 已安装版本继续提供 AES、ChaCha20、Argon2id 及密钥解析；[PyCA 项目](https://github.com/pyca/cryptography) | oracle 原语及合成密钥检查，不进入生产核心 |
| argon2-cffi | 25.1.0；MIT | [PyPI 固定版本](https://pypi.org/project/argon2-cffi/25.1.0/) 发布于 2025-06-03；只调用 low_level.hash_secret_raw 的 Type.D | reader.py 内的 Argon2d 适配；不使用密码编码字符串或默认密码策略 |
| argon2-cffi-bindings | 26.1.0；MIT，捆绑实现许可证随 wheel 保留 | [PyPI 固定版本](https://pypi.org/project/argon2-cffi-bindings/26.1.0/) 发布于 2026-08-20；macOS arm64 的二进制 wheel | 项目内 Python 测试后端，不自行编译或下载 C 工具链 |
| keepass（keepass-rs） | =0.15.3；MIT | [固定源码](https://github.com/sseemayer/keepass-rs/tree/15afd4da3d2f305069c7940795af1de9645fd81c)，仅开启 save_kdbx4；上游仍将保存标为实验性且仅写 4.1 | 独立 tests/reference_writer 进程；不链接 Flutter/Web，不代表生产选型 |
| keepassxc-cli | 2.7.12；GPL-2.0/3.0 | 本机已有程序，作为已知参考读者和原始合成来源 | 外部进程调用，不复制或链接其实现 |

Python 新增的两个包仅安装到项目 tests/kdbx_oracle/.deps-argon2；cffi 2.0.0、pycparser 3.0 与 cryptography 46.0.4 复用原解释器。requirements.txt 固定版本，[macOS arm64 锁文件](../../tests/kdbx_oracle/requirements-argon2-macos-arm64.lock) 固定来自 PyPI 的 wheel SHA-256；安装使用 --only-binary=:all:、--require-hashes、--no-deps 和 --target，没有改全局 Python 包。该 wheel 锁不宣称跨平台通用。

最初 mise Python 的复制式 venv 在 ensurepip 中失败，符号链接 venv 的可执行入口被工作区规则拒绝。没有修改命令白名单或绕过受保护路径；最终使用已允许的原解释器与项目内 --target 安装，session dfced2c1-68f2-4e62-a8ab-0234ceb5313d，exit 0。未安装新工具链。

Rust 使用已有 Cargo/Rust 1.98.0。Cargo.toml 固定直接版本，Cargo.lock 固定完整解析和 registry 校验和；初次构建沿用用户已有 rsproxy registry 配置，没有改 Cargo 配置。后续生成前强制 locked/offline build，并固定 target-dir，防止源码更新后误用旧二进制。全图 cargo metadata 的离线查询因未缓存的非本机依赖 cc 1.8.0 未完成；没有为此下载其它平台依赖，不将这次查询当成完整传递许可证或供应链审查。

## Argon2 与解析检查

[官方 low-level API](https://argon2-cffi.readthedocs.io/en/stable/api.html) 的 hash_secret_raw 接受 Type.D 和显式版本；KDBX S/P/M/I/V 的宽度、内存字节单位与参数字典见 [KDBX 4 规范](https://keepass.info/help/kb/kdbx_4.html)。

| 路径 | 已核对行为 |
| --- | --- |
| Argon2d | v16、v19 实际后端向量通过；缺少依赖时明确 Unsupported，AES/Argon2id 仍可用 |
| Argon2id | 继续使用 cryptography；v19 向量、既有公开文件及非空 K/A 参数传递通过 |
| 类型与取整 | S 为字节数组、P/V 为 UInt32、M/I 为 UInt64；拒绝 bool、带符号或错误宽度。M 保留原字节元数据，传后端时取 M // 1024，不额外改为 4 × P 的倍数 |
| 最低参数 | 盐至少 8 字节、P/I 至少 1、M // 1024 至少 8 × P |
| 测试资源预算 | M ≤ 1 GiB、I ≤ 64、P ≤ 16，且 (M // 1024) × I ≤ 2 × 1024 × 1024 KiB；盐/K/A 各 ≤ 1 MiB |
| 字典解析 | 每个 key/value 长度先检查边界；畸形 UTF-8、重复键、错误数值长度、缺失终止及终止后数据明确拒绝 |
| XML 配置 | max_xml_bytes 与 gzip limit 必须是合法正整数且不超过全局上限，bool 也拒绝；在解析/解压前执行 |

上述预算只限制合成测试工具；不是 K014/K015 的生产参数校准、取消机制、时限或设备预算。Argon2d 的非空 K/A 仍明确拒绝，因为所用 raw 接口不提供这两个独立参数；Argon2id v16、其它算法和更广泛畸形输入仍不在支持范围。没有宣称所有 zlib/base64 等既有错误路径已经统一为项目异常。

向量来源固定到官方版本：

- [argon2-cffi 16.0.0 测试](https://github.com/hynek/argon2-cffi/blob/1112a2e58336e549f8efb7f2d747f5249f85f6be/tests/test_low_level.py)：D v16。
- [argon2-cffi 25.1.0 测试](https://github.com/hynek/argon2-cffi/blob/1fcae4fc1b7ff192b5ade54f6616771e5cf5f391/tests/test_low_level.py)：D v19 与 id v19。

上游原件 Argon2ChaCha.kdbx 现已由 oracle 完整解码：KDBX 4.0、外层/内层 ChaCha20、Argon2d v19、M=24576 字节、I=2、P=3。三个原件都核对 8 个分组、4 个当前条目、2 个历史、1 个删除对象和 15 字节附件；错误密码/密钥文件、损坏密文均拒绝，KeePassXC 交叉读取通过。原始 writer/version 仍未知，原始 SHA-256 和 Git blob 哈希不变。

## Rust 参考保存的实际结果

输入使用上一批已登记的 m41-passkey-edit1.kdbx 与 v41-vault-edit1.kdbx，各自已有目标历史。它们来自 KeePassXC 2.7.12；其首次导入相对确定性源的既有差异继续保留在原清单中，没有重新定义源基线。

| 输入 | 新输出组合 | 当前条目 / 分组 | 总历史 | 附件池 / 总内容 | 关系 / 规则 / 事件 |
| --- | --- | --- | --- | --- | --- |
| 同 RP 多 Passkey | AES-KDF、Argon2d、Argon2id 各搭配 AES、ChaCha20 | 39 / 9 | 4 → 5 | 6 / 3300 字节 | 22 / 1 / 2 |
| 个人资料领域库 | 同上六组 | 36 / 9 | 4 → 5 | 6 / 3300 字节 | 22 / 1 / 2 |

AES-KDF 显式设为 1000000 轮；Argon2d/id 显式设为 v19、8 MiB、2 次、并行 1。以上只是参考算法夹具，不是生产推荐或性能比较；未改原输入 KDF。每份输出均为 KDBX 4.1，密码和目标 UUID 来自公开合成案例。

每份都有 9 条未忽略的语义差异。单字段编辑与历史位置变化之外，另有三条差异：根分组内 Group/Entry 的顺序变化，以及原网站分组和登录条目的两个默认 IconID 移除。新历史插在开头，原有历史相对顺序及完整快照保留；history_snapshot_changes 均为空。每个清单项明确 lossless_roundtrip=false，没有为了通过而扩展语义忽略规则。

Rust HashMap 还改变了 9 份输出中部分当前/历史附件的原始排列，共 12 处观察。既有语义规范不区分 Binary 排序，因此另存 attachment_order_changes。附件名称、全部字节、池保护位和重复次数仍严格比较；池项数与内容摘要一并核对。三把同 RP 凭据继续保有独立 P-256 公钥、credential ID、user handle 和 parent 配对。

KeePassXC 2.7.12 能重新打开全部 12 份输出，当前/历史字段和保护位交叉一致。它的 4.x XML 导出不含完整附件池，因此清单明确 attachment_pool_cross_checked=false；附件结论来自原输入和独立 oracle 的逐字检查，不能冒充 CLI 附件导出证据。

## 验证、失败与追溯

| 检查 | 实际结果 / 会话 |
| --- | --- |
| 24 项 KDF/解析边界 | 0.188 秒通过；b2f4c782-0e75-4d3c-a64c-ec49d06d9474 |
| 9 项上游原件 | 0.223 秒通过；a70c6e98-9c44-469d-9052-75069f6affaa |
| Rust 初次构建 | 15.185 秒，exit 0；408bd9e5-0e21-4b7e-939c-ae0020fc0a16 |
| 格式化后锁定离线构建 | exit 0；aced883b-5287-441c-852e-70e807b1e9de |
| 12 份生成 + 独立核对 + CLI 导出 | 3.789 秒，exit 0；f1730d01-ded2-40b8-a1b7-8a977186f496 |
| 15 项参考产物/失败保护 | 5.015 秒通过，无跳过；7bad05b3-060d-4224-bbb9-f8cfb646f162 |

首次矩阵生成因附件列表顺序严格相等而失败，session eaa3e99c-4a78-403e-82d7-bb0ed95d206d；没有登记部分成功。核对固定上游源码及实际附件名称/摘要/保护位后，改为保留重复次数的内容比较并单列原始排序，同时收紧新增空标准字段的保护位要求。再次生成才得到以上 12 份固定产物。

review_matrix_design 只读复核 reader，reference_writer_library 只读复核 helper/generator；发现的依赖 provenance 遗漏、附件重排和旧二进制追溯问题已修正。没有把模型复核当成人工独立批准。

生成后仅为 generator 增加 locked/offline build、源变化拒绝与案例参数检查，没有重写 12 份 KDBX 或变更 Rust 源码。清单分别保留 generation_provenance 和当前 provenance，记录原构建/生成会话和 generation_binary_sha256；测试固定两者仅有 generator 文件不同。已有清单重跑只核对来源/产物哈希和范围，不构建、不写文件。

失败保护实际覆盖：同路径/已有目标拒绝覆盖；密码、UUID、算法、未变化字段和 3.1/4.0 输入拒绝；字段值/保护位、附件或历史破坏使保留检查失败；清单创建异常后仅清理本次新建产物。清单失败采用调用层注入，未实测磁盘写满、fsync 故障或强杀。强杀可能留下锁、部分清单或未登记输出，下次停止并拒绝覆盖；不是生产原子保存或自动恢复承诺。

## 最终复跑与后续边界

在本页及关联文档完成后，从仓库根目录执行：

~~~sh
python3 -B tests/run_python_tests.py --suite oracle
python3 -B tests/run_python_tests.py --suite domain
python3 -B tests/reference_writer/generate.py
python3 -B tests/fixtures/kdbx/matrix_generate.py
cargo build --locked --offline --release --manifest-path tests/reference_writer/Cargo.toml --target-dir tests/reference_writer/target
cargo fmt --manifest-path tests/reference_writer/Cargo.toml -- --check
python3 -B adr/design/verify.py
python3 -B adr/design/verify_ios.py
python3 -B adr/verify_personal_vault.py
git diff --check
~~~

最终统一回归与无后续文件写入的验收记录由任务 2aa485d1e10c40d1bb636c1126a7c369 保存；此前 159 项、10k Mac 时间/RSS 属于上一批证据，不当成本轮 Rust 或 Argon2 的性能量测。

继续补官方 KeePass/KeeAgent/移动参考客户端、4.x 不压缩/资源攻击、未覆盖参数、秘密扫描和设备/Web 预算。Rust 参考实验尚有明确语义差异；双候选读改写、跨客户端再编辑、故障/取消/并发/恢复及生产授权仍须按 K003/K009 和 G0/GV/GW 门槛实施。

回滚仅撤销本批新增测试依赖声明、reader 增量、reference_writer、12 份 rs41 样本、该清单/新测试和对应精确忽略项及文档增量；不得重置整仓库或删除此前样本。全程只使用公开合成资料，没有执行账户、金融、通信或凭据注册操作，没有 commit/push。

