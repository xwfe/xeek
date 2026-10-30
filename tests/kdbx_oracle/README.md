# kdbx_oracle：KDBX 测试对照工具

只读的 KDBX 解码器和语义比较器，给 K002 样本和 K003 无损测试当“独立裁判”。**不是 keex 的生产实现，不写 KDBX，只用于合成数据**——真实密码库不要交给它（[真实数据规则](../../adr/REAL_DATA_RULES.md)）。

## 怎么跑

需要 Python 3.12、固定 cryptography 和 Argon2 后端（版本见 requirements.txt）。从仓库根目录运行，入口自动加载项目内测试依赖：

~~~sh
python3 -B tests/run_python_tests.py --suite oracle
python3 -B tests/run_python_tests.py --suite domain
~~~

当前 oracle 入口 190 项，领域 93 项，共 283 项；另有 Rust 保存版本探针 3 项、隔离补丁 API 测试 15 项（附件生命周期 4 项、未知内容 3 项、历史裁剪 5 项），不混入 Python 数量。缺少 Argon2 后端时入口直接报错。旧交叉读/live 类仍有明确跳过条件，跳过不算完整验收；K003 最小反例集要求已有 Cargo、Dart、KeePassXC 和固定项目缓存，缺任一项直接失败。只跑领域检查仍可使用 --suite domain。

K003 最小反例及直接上游版本探针：

~~~sh
python3 -B tests/run_python_tests.py --suite oracle --pattern test_candidate_minimal.py -v
cargo test --locked --offline --release --manifest-path tests/reference_writer/Cargo.toml --target-dir tests/reference_writer/target --test save_versions
~~~

最小反例集每次先按锁文件离线构建两个真实 helper，再现场构造小输入；Dart 构建仅在子进程将 PUB_HOSTED_URL 固定为锁文件的 https://pub.dev，不继承其它镜像的缓存目录，也不更改全局环境。KeePassXC 只验证输入可打开，丢失判断使用独立 oracle；新密码库只放临时目录并自动清理。**测试通过表示固定版本的缺陷被准确复现，不能解释为 writer 无损通过。** 反例、源码定位与修补范围见 [K003 最小反例证据](../../adr/evidence/K003_MINIMAL.md)。

隔离 Rust 保留补丁的构建与专项入口见 [实验说明](../rust_preservation/README.md)。专项每次真实构建并运行 Rust API 测试，再做 26 次往返；原 12 组矩阵按完整期望树比较已无差异；构造的组/条目交错按 KeePass 写法规范为先条目后子组并精确断言；未知内容拒绝保存或拒绝打开；历史裁剪另与 KeePassXC 编辑同一输入对照；补丁库和 KeePassXC 轮流编辑的完整往返见 test_rust_third_party.py，文件头设置见 test_rust_header.py。原未修候选诊断仍保留。修复与未解决边界见 [补丁证据](../../adr/evidence/K003_RUST_PATCH.md)。

本机使用项目内 --target 安装，复用现有 cryptography/cffi/pycparser，不改全局包。macOS arm64 固定 wheel 锁的复现命令：

~~~sh
python3 -B -m pip --isolated --disable-pip-version-check install --no-cache-dir --only-binary=:all: --require-hashes --no-deps --index-url https://pypi.org/simple --target tests/kdbx_oracle/.deps-argon2 -r tests/kdbx_oracle/requirements-argon2-macos-arm64.lock
~~~

该锁只适用于记录的 macOS arm64 wheel。其它环境按 requirements.txt 准备固定版本并登记对应平台哈希。Rust 合成参考 helper 见 [构建说明](../reference_writer/README.md)。

在仓库根目录查看摘要或比较两个合成库：

~~~sh
PYTHONPATH='tests/kdbx_oracle/.deps-argon2:tests/kdbx_oracle' KX_PW='合成密码' python3 -B -m kdbx_oracle summary --password-env KX_PW 库.kdbx
PYTHONPATH='tests/kdbx_oracle/.deps-argon2:tests/kdbx_oracle' KX_PW='合成密码' python3 -B -m kdbx_oracle diff --password-env KX_PW A.kdbx B.kdbx
~~~

- 密码只读环境变量或提示输入，不接受命令行参数。密钥文件用 --keyfile，只用密钥文件时加 --no-password；B 库密钥不同就用 --b-keyfile / --b-password-env。
- summary 只输出计数、字段名和附件 SHA-256，不输出字段值。
- diff 退出码：0 无差异，1 有差异，2 打不开。受保护值默认只报长度，--reveal 才显示内容，只对合成样本用。
- 比较默认保留全部差异；固定样本排除参考客户端动态元数据时，只使用已审查的精确路径，不能用宽泛键名前缀掩盖未知字段。

## 比较器认为什么算“一样”

完整规则只写在 `kdbx_oracle/semantic.py` 开头。要点：加密随机数、附件池编号、时间写法、字段先后、标签顺序、**已知**的空元素这类只影响字节的东西不报；不认识的元素（哪怕是空的）、保护标记、分组和条目顺序、历史都报。附件内容和附件保护标记分开报（manifest 里是 `changed/value` 和 `changed/attrs`）。哪些差异是“改了就该变”的，由测试自己用 `--ignore` 列出来，比较器不替人猜。

2026-10-18 增补：规范化只沿实际 KeePassFile 的已知结构进行；布尔值使用明确字段白名单，Name/Notes/未知子树的大小写、混合正文与尾随文字不折叠。未知节点参与的子节点序列按原顺序比较；空标准字段含未知属性、子节点或重复 Key/Value 时保留。重复键路径后缀与字段中的字面 # 使用不同编码。时间的小数部分不舍入，受保护值在另一版本丢失保护标记或由父节点继承保护时仍默认隐藏。

比较器仍把 Meta/Binaries 的已引用内容折入附件摘要、跳过容器 HeaderHash；未引用附件池项、池上的未知元数据和容器字段不是本轮语义比较的无损承诺，HeaderHash 完整性由解码器另行校验。K003 不能只凭这一个语义 diff 放行 writer。修复和反例见 [K002 增量证据](../../adr/evidence/K002.md)。

## 为什么要自己读，不用 KeePassXC

K003 要判断候选库有没有丢数据。如果用 KeePassXC 读两边的文件，KeePassXC 读取时自己丢掉的东西两边都看不见，结论会是假的“无损”。KeePassXC 2.7.12 实际会丢什么、改什么，见[样本说明](../fixtures/kdbx/README.md)里的“KeePassXC 2.7.12 写库时自己改了什么”。

## 实现了哪些

下表列出当前路径。固定原件已验证 4.0 Argon2id/AES、3.1 外层 ChaCha20/AES-KDF 与 4.0 Argon2d/外层 ChaCha20；另有 12 组 KDBX 4.1 参考保存覆盖三种 KDF × 两种外层密码。资源、参数与剩余差异见 [K002_LIBRARIES](../../adr/evidence/K002_LIBRARIES.md)；原件来源见 [算法证据](../../adr/evidence/K002_ALGORITHMS.md)。这不代表全部版本/参数或生产 writer 已通过。

| 项 | 实现 | 说明 |
| --- | --- | --- |
| 格式 | KDBX 3.x、4.0、4.1 | 高于 4.1 直接拒绝 |
| 密钥 | 密码、密钥文件、两者组合 | 密钥文件按 KeePassXC 2.7.12 `FileKey.cpp` 的顺序判定：XML（1.0 base64、2.0 十六进制且必须有 Hash）→ 恰好 32 字节 → 恰好 64 个十六进制字符 → 整个文件取 SHA-256。含 DOCTYPE 或非 UTF-8 的文件不当 XML 解析，这是和 KeePassXC 唯一的差别 |
| KDF | AES-KDF、Argon2d、Argon2id | Argon2d 使用固定 argon2-cffi 后端支持 v16/v19，非空 K/A 明确拒绝；Argon2id 沿用 cryptography，仅支持 v19，保留 secret/ad 参数路径 |
| 外层加密 | AES-256-CBC、ChaCha20 | Twofish 不支持（KeePass 2.x 里是插件，KeePassXC 原生支持） |
| 压缩 | gzip、不压缩 | |
| 内层保护流 | Salsa20（自写，见 `salsa20.py`）、ChaCha20 | ArcFour 不支持 |
| XML | 只收 UTF-8；任何位置出现 DOCTYPE/ENTITY 就拒绝 | UTF-16 的 DOCTYPE 按 UTF-8 字节搜不到、却会被 expat 展开，所以先卡编码；KeePass 只写 UTF-8 |
| 资源上限 | 解压/XML 256 MiB（调用方只可调小）、XML 嵌套 256 层、AES-KDF 2^32 轮、文件 64 MiB；Argon2 M ≤ 1 GiB、I ≤ 64、P ≤ 16、(M // 1024) × I ≤ 2 × 1024 × 1024 KiB，盐/K/A 各 ≤ 1 MiB | KDF 前拒绝错误类型/范围；XML/gzip limit 必须为正整数且不是 bool。只是合成测试预算，不是生产时限、取消机制或 K014/K015 参数策略 |
| 完整性 | 4.x 头部 SHA-256 + 头部 HMAC + 分块 HMAC，拒绝结束块后的多余数据；3.x StreamStartBytes + 填充 + 块哈希 + HeaderHash | 3.x 先比 StreamStartBytes 再去填充，所以截断报“文件坏了”而不是“密码错”。HeaderHash 不符就拒绝；缺失时 `header_hash == "missing"`，调用方应只读（[威胁模型](../../adr/THREAT_MODEL.md) T1） |

## 4.x 认证负载与资源反例

[278 案配方](../fixtures/kdbx/v4_payload_manifest.json)覆盖 4.0/4.1 × AES/ChaCha20；8 个安全正例含 gzip/不压缩，270 个负例检查 HMAC、gzip、内层头部、XML、base64、算法、AES 填充与密文长度。每个负载负例重新认证，测试观察实际拒绝层；26 项新增测试及八个 CLI 正控制见 [K002_RESOURCES](../../adr/evidence/K002_RESOURCES.md)。

gzip 底层错误转换为 KdbxIntegrityError，XML base64 错误转换为不带输入值的 KdbxFormatError。重复内层流配置、非空结束字段按本 oracle 策略拒绝；多个附件仍保留。4.x gzip 预算包含内层头与 XML，不压缩预算针对 XML 本身并受文件上限约束；不是生产内存或取消策略。

## 错误类型

| 异常 | 意思 |
| --- | --- |
| `KdbxKeyError` | 密钥错误，或头部/密文被改——这一步在格式上分不出是哪种 |
| `KdbxIntegrityError` | 密钥对，但内容被改、被截断或有多余数据 |
| `KdbxFormatError` | 不是 KDBX、字段缺失、长度不对 |
| `KdbxUnsupported` | 合法但本工具不支持，或超过测试上限 |

## 依赖登记

AGENTS.md 要求登记版本、许可证、维护情况和替换边界。以下均为合成测试依赖，不进入 keex 产品；完整实测见 [K002_LIBRARIES](../../adr/evidence/K002_LIBRARIES.md)。

| 依赖 | 许可证 | 固定版本 | 维护情况 | 替换边界 |
| --- | --- | --- | --- | --- |
| [cryptography](https://github.com/pyca/cryptography)（Python 库） | Apache-2.0 OR BSD-3-Clause | 46.0.4，见 `requirements.txt` | PyCA 维护，持续发版；本机本来就装着，没有为此新装 | 只用 AES-CBC、ChaCha20、Argon2id、PKCS7、以及测试里读回 Ed25519/P-256 密钥。换成任何提供这些原语的库都只动 `reader.py` 和 `tests/fixtures/kdbx/source.py` |
| keepassxc-cli（外部程序） | GPL-2.0/3.0 | 2.7.12（样本就是用它生成的） | KeePassXC 项目持续发版 | 只当外部程序调用来生成样本和做对照，不链接、不复制它的代码；没装时对照测试跳过，重新生成样本不可用 |
| [argon2-cffi](https://pypi.org/project/argon2-cffi/25.1.0/) | MIT | 25.1.0 | 官方固定发布版；本轮按用户授权装在项目测试目录 | 仅 reader.py 的 Type.D / 显式版本 raw KDF 适配 |
| [argon2-cffi-bindings](https://pypi.org/project/argon2-cffi-bindings/26.1.0/) | MIT，捆绑实现许可证随 wheel 保留 | 26.1.0 | 官方 2026-08-20 发布；macOS arm64 wheel SHA-256 固定 | 复用 cffi 2.0.0 / pycparser 3.0，不安装 C 工具链 |
| [keepass 参考 helper](../reference_writer/README.md) | MIT | =0.15.3 + Cargo.lock | 固定源码与实际构建已验证；上游保存仍标实验性且仅写 4.1 | 独立合成参考进程，不影响 oracle 只读职责，不代表生产选型 |
| [Playwright](../web_storage/README.md) | Apache-2.0 | 1.64.1（pnpm-lock.yaml） | 微软维护，发版频繁 | 只驱动 K071 浏览器实验，装在实验目录，不进产品；换驱动只影响 drive.mjs |
| [kdbx.dart 候选 helper](../dart_candidate/README.md) | **GPL-3.0** | kdbx 2.5.0 + pubspec.lock（38 个传递依赖） | 2.5.0 约 2026-08 发布；依赖装在项目内 `.pub-cache/` | 独立 K003 候选进程，不链接进 oracle 或产品；实测见 [K003](../../adr/evidence/K003.md) |
