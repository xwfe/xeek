# KDBX 合成与公开测试样本

这里的 `.kdbx`、`.keyx`、`.key` 都是合成或上游已公开的测试原件，公开凭据记录在各自清单中。keex 自行生成的 SSH/Passkey 私钥由公开种子派生，只测编码和保留，**绝不能**授权给任何主机或注册到网站。

## 怎么用

原 K002 的37份样本使用 manifest.json；K069 首批九份 v*-vault 文件使用 vault_manifest.json；新增17份 m*-passkey / m41-scale 文件使用 matrix_manifest.json。入口见 [领域测试说明](../../vault_domain/README.md) / [规模证据](../../../adr/evidence/K069_MATRIX.md)。另有三份固定算法原件及密钥文件，使用 [upstream_kdbxweb/manifest.json](upstream_kdbxweb/manifest.json)，来源和限制见 [算法证据](../../../adr/evidence/K002_ALGORITHMS.md)。另有 12 份 rs41-*.kdbx 使用 [rust_writer_manifest.json](rust_writer_manifest.json)，由固定 keepass 0.15.3 生成；参数、剩余差异和失败保护见 [成熟库实验](../../../adr/evidence/K002_LIBRARIES.md)。新增四份 v4*-rich-*-uncompressed.kdbx 使用 [v4_payload_manifest.json](v4_payload_manifest.json)，包含 278 个可重建配方；见 [4.x 资源证据](../../../adr/evidence/K002_RESOURCES.md)。当前共 82 份留存 KDBX，原 78 份字节保留。以下旧样本表及生成命令专指原 K002。

- 每个样本的密码、密钥文件、SHA-256、预期结果和结构摘要都在 `manifest.json`。摘要由 [kdbx_oracle](../../kdbx_oracle/README.md) 算出，不含字段值。
- 回归测试：从仓库根目录执行 python3 -B tests/run_python_tests.py --suite oracle。核对哈希、摘要、参考写入差异、关键字段与保护、损坏拒绝及 CLI 交叉读；固定依赖和当前 131 项入口见 [oracle 说明](../../kdbx_oracle/README.md)。领域与规模另执行 --suite domain，共 93 项。
- 给 keex 自己的测试（K003 起）用时，以 manifest 里的 `expect` 为准，用 `kdbx_oracle diff` 对比语义。

## 4.x 认证负载增量

~~~sh
python3 -B tests/run_python_tests.py --suite oracle --pattern test_v4_payload.py
python3 -B tests/fixtures/kdbx/v4_payload.py
~~~

278 个配方中有 8 个正例和 270 个负例。四份不压缩正例留存，其余现场重建，不把配方数当成留存文件数或 unittest 方法数。工具只读固定公开源，生成时复用公开密钥/确定 IV；它是测试变异器，不提供用户库保存能力。清单固定源/代码/实际运行时版本及每案哈希。已有清单重跑不写入，未登记输出或不同清单拒绝覆盖；普通异常只清理本次创建的文件，不承诺强杀恢复。

## 怎么重新生成

```sh
python3 -I tests/fixtures/kdbx/generate.py                 # 只补还不存在的样本
python3 -I tests/fixtures/kdbx/generate.py --only G41-RICH --force   # 重做指定样本
```

需要 `keepassxc-cli`（现有样本用 2.7.12 生成）和 Python `cryptography`。**重做一定会改变文件字节**（KeePassXC 每次随机生成种子和 IV），提交前要说明原因；用别的 KeePassXC 版本重做时，`writer_changes` 可能变，那本身就是要记录的兼容性信息。

密码库和密钥默认被 .gitignore 排除。原 K002 已登记文件保持现状；新增公开样本核对来源和哈希后仅逐文件添加精确放行规则，不放开任意密码库。

损坏样本由 `mutate.py` 从黄金样本变异而来，字节完全确定：

```sh
python3 -I tests/fixtures/kdbx/mutate.py
```

**重做了 G31-RICH 或 G41-RICH 以后必须重跑它**，否则测试里的 `test_mutations_are_reproducible` 会报哈希不符——那不是解码器坏了，是损坏样本还是从旧黄金样本变异的。

改了比较器以后，用 `python3 -I tests/fixtures/kdbx/generate.py --refresh` 重算 manifest 里的摘要和写入差异，不要用 `--force` 重做样本。

## 样本矩阵

样本源分两类：

- `xml-import`：`source.py` 确定性地生成 KeePass 明文 XML，再用 `keepassxc-cli import` 加密。只放目标版本支持的特性，KeePassXC 就会正好写成那个版本。
- `cli-ops` / `cli-keyfile`：只用 keepassxc-cli 命令建库，得到 KeePassXC 自己产生的历史、回收站等结构。

| ID | 格式 | 来源 | 凭据 | 覆盖 |
| --- | --- | --- | --- | --- |
| G31-RICH | 3.1 | xml-import | Unicode 密码 | 历史（含受保护字段增删）、回收站、DeletedObjects、共享附件、未知受保护字段、KeeAgent（设置 + ed25519 私钥附件）、三种 OTP 写法、Passkey（KPEX_ 字段和旧名 KPXC_PASSKEY_USERNAME）、字段引用、自定义图标、过期条目、三层嵌套、Unicode/空字段/87 KB（6.3 万字符）备注/4096 字受保护长字段 |
| G40-RICH | 4.0 | xml-import | Unicode 密码 | 同上，加元数据/分组/条目 CustomData |
| G41-RICH | 4.1 | xml-import | Unicode 密码 | 同上，加 QualityCheck、PreviousParentGroup、分组标签、图标名称、CustomData 时间 |
| G31-BIG | 3.1 | xml-import | 密码 | 1.2 MB 不可压缩附件，跨 1 MiB 哈希块边界 |
| G41-BIG | 4.1 | xml-import | 密码 | 1.2 MB 不可压缩附件，跨 1 MiB HMAC 块边界 |
| G41-CLI | 4.1 | cli-ops | 密码 | KeePassXC 自己生成的历史、附件、回收站、永久删除 |
| G31-KEYXML | 3.1 | cli-keyfile | 密码 + XML 2.0 密钥文件 | 组合密钥 |
| G31-KEYONLY | 3.1 | cli-keyfile | 只有 XML 2.0 密钥文件 | 无密码 |
| G31-KEYXML1 | 3.1 | cli-keyfile | 密码 + XML 1.0 密钥文件 | KeePass 2.x 旧式 base64 密钥文件 |
| G31-KEYRAW32 | 3.1 | cli-keyfile | 密码 + 32 字节二进制密钥文件 | 密钥文件原样当密钥的路径 |
| G31-KEYBIN | 3.1 | cli-keyfile | 密码 + 64 字节二进制密钥文件 | 密钥文件取 SHA-256 的路径 |
| G31-KEYHEX | 3.1 | cli-keyfile | 密码 + 64 位十六进制密钥文件 | 密钥文件直接当 32 字节密钥的路径 |

错误密码、缺少密钥文件不单独存文件，测试里对每个样本动态验证。

### 损坏与攻击样本

预期：`reject` = keex 必须拒绝打开、不写回；`read-only` = 可以打开，但必须只读；`open` = 变异后仍是合法库，内容和基础样本完全一致。密码同基础样本。

每个样本只让它声称的那一项检查拦住：比如 R41-HEADER-HMAC 重算了 SHA-256，补上正确的头部 HMAC 就能打开。“oracle”列是 kdbx_oracle 的异常，异常信息里必须出现的片段登记在 manifest 的 `oracle_reason`。keex 的错误分类不必一样，但不能把“文件被改”当成可以继续写的状态。“KeePassXC”列是 2026-10-16 用 keepassxc-cli 2.7.12 `ls` 实测的结果。

| ID | 基于 | 怎么改 | 预期 | oracle | KeePassXC 2.7.12 |
| --- | --- | --- | --- | --- | --- |
| R31-TRUNC-HALF | G31-RICH | 截掉后一半（不对齐） | reject | FormatError | 拒绝 |
| R31-TRUNC-ALIGNED | G31-RICH | 在 16 字节边界截断 | reject | IntegrityError | 拒绝 |
| R31-TRUNC-HEADER | G31-RICH | 断在头部字段中间 | reject | FormatError | 拒绝 |
| R31-TRAILING | G31-RICH | 密文后追加 22 字节 | reject | FormatError | **打开** |
| R31-TRAILING-ALIGNED | G31-RICH | 密文后追加 32 字节 | reject | IntegrityError | **打开** |
| R31-CIPHER-FLIP | G31-RICH | 密文中间翻转 1 位 | reject | IntegrityError | 拒绝 |
| R31-HEADERHASH-MISMATCH | G31-RICH | 交换两个头部字段的位置，值和密文不变 | reject | IntegrityError | 拒绝（Header doesn't match hash） |
| R31-HEADERHASH-MISSING | G31-RICH | 去掉 Meta/HeaderHash 后重新加密 | **read-only** | 打开，`header_hash == "missing"` | 打开 |
| R31-AESKDF-HUGE | G31-RICH | AES-KDF 轮数改成 2^62 | reject | Unsupported | 拒绝 |
| R31-CIPHER-UNKNOWN | G31-RICH | 算法改成未知 UUID，内容仍是 AES，HeaderHash 已更新 | reject | Unsupported | 拒绝 |
| R31-GZIP-BOMB | G31-RICH | 解压后 512 MiB（文件 0.5 MB） | reject | Unsupported | 拒绝（用时 2.6 秒） |
| R31-XML-ENTITY | G31-RICH | 实体展开炸弹 | reject | FormatError | 拒绝 |
| R31-XML-EXTERNAL | G31-RICH | 外部实体指向 `file:///etc/hosts` | reject | FormatError | 拒绝 |
| R31-XML-DEEP | G31-RICH | 10 万层嵌套 Group | reject | FormatError | **段错误崩溃** |
| V31-UNCOMPRESSED | G31-RICH | 压缩标志改成 0、不压缩重新加密、HeaderHash 已更新 | open | 打开，内容同 G31-RICH | 打开 |
| R41-TRUNC-HALF | G41-RICH | 截掉后一半 | reject | FormatError | 拒绝 |
| R41-TRAILING | G41-RICH | 结束块后追加 22 字节 | reject | IntegrityError | **打开** |
| R41-HEADER-FLIP | G41-RICH | 主种子翻转 1 位，不重算 SHA-256 | reject | IntegrityError | 拒绝 |
| R41-HEADER-HMAC | G41-RICH | 插入 PublicCustomData 并重算 SHA-256 | reject | KeyError | 拒绝（HMAC mismatch） |
| R41-BLOCK-FLIP | G41-RICH | 第 0 块密文翻转 1 位 | reject | IntegrityError | 拒绝（报的是内层头部错误，不是 HMAC） |
| R41-ARGON2-HUGE | G41-RICH | KDF 改成 Argon2id、内存 1 TiB，重算 SHA-256 | reject | Unsupported | **20 秒内没有返回** |
| R41-AESKDF-HUGE | G41-RICH | AES-KDF 轮数改成 2^62，重算 SHA-256 | reject | Unsupported | 拒绝 |
| R42-VERSION | G41-RICH | 版本号改成 4.2，重算 SHA-256 和头部 HMAC | reject | Unsupported | **打开** |
| R-KDB1 | G31-RICH | 签名改成 KeePass 1.x | reject | Unsupported | 拒绝 |
| R-NOT-KDBX | — | 256 字节伪随机数 | reject | FormatError | 拒绝 |

几个容易踩的坑：

- **keex 比 KeePassXC 严是有意的。** 尾部多出数据、声称 4.2 的库，KeePassXC 2.7.12 都照常打开；keex 按 [ADR-0001](../../../adr/0001-flutter-kdbx-architecture.md) §3 和威胁模型 T1 拒绝。做 K003 往返时不要拿 KeePassXC 能不能打开来判断这些样本。
- **R31-XML-DEEP 会让 KeePassXC 崩溃，R41-ARGON2-HUGE 会让它卡住**。自动化对照里不要让 KeePassXC 打开它们，或者加超时。
- **R41-HEADER-HMAC 的报错和“密码错”一样。** 头部被改且重算了 SHA-256 时，只有头部 HMAC 会失败，而 HMAC 失败在格式上分不出是密钥错还是头部被改。keex 的提示不要断言“密码错误”。
- **3.1 的截断要先确认密钥再判断。** 先比 StreamStartBytes，对上了再去填充；顺序反了，R31-TRUNC-ALIGNED 会被报成“密码错”，用户会反复试密码。
- **超大 KDF 参数必须在跑 KDF 之前拒绝。** 4.x 要先核头部 SHA-256、再查参数上限、最后才跑 KDF；3.1 头部没有校验，只能靠参数上限。顺序反了，R31-AESKDF-HUGE 会让客户端卡到天荒地老。
- **尾部污染在 4.x 里密码学上发现不了。** 结束块之后的字节不在任何 HMAC 里，只能靠“结束块后必须是文件末尾”这条规则拒绝。
- **压缩炸弹测试里用 16 MiB 上限**，省得每次解出 256 MiB。keex 自己的上限由 K015 定。

## KeePassXC 2.7.12 写库时自己改了什么

把源 XML 和生成的库做语义比较得到（逐条路径见 manifest 的 `writer_changes`）。做 K003 无损对照时要知道这些是 KeePassXC 的行为，不是候选库的：

- **4.x 下所有附件都被标成受保护**（内层头部标志位），3.1 不标。
- **4.1 下分组和条目 CustomData 的 `LastModificationTime` 被丢掉**，元数据 CustomData 的保留。
- 设了自定义图标的分组，标准图标号 `IconID` 被改成 0。
- 4.x 下新增 `Meta/SettingsChanged`；3.1 下新增它自己的 `Meta/CustomData`（`KPXC_RANDOM_SLUG`、`_LAST_MODIFIED`）。
- 标签被排序、分隔符从 `;` 改成 `,`；缺省的空元素和空标准字段被补齐。这两条比较器视为语义相同，不列在 `writer_changes` 里。
- 按格式升级：条目有 CustomData → 4.0；有 QualityCheck、PreviousParentGroup 等 4.1 特性 → 4.1；否则 3.1。`keepassxc-cli rm` 把条目移进回收站会写 PreviousParentGroup，所以 G41-CLI 是 4.1。

## 还没覆盖的（请别当成已验证）

| 缺口 | 原因 | 怎么补 |
| --- | --- | --- |
| 未覆盖的 KDF 参数及其它算法组合 | Argon2d v16/v19 与三份上游原件已验证；新增 4.1 三种 KDF × 两种外层密码参考保存。Argon2d 非空 K/A 等仍拒绝，参考保存尚有顺序/IconID 差异 | 继续补固定版本官方/移动客户端与参数范围；本轮已授权依赖及限制见 K002_LIBRARIES |
| 参考客户端写的不压缩库 | 3.1 和新增四份 4.x 不压缩变体均由测试工具重新封装，KeePassXC 可打开；没有新增客户端原生写出证据 | 用有版本的参考客户端生成并登记 |
| KeePass 2.x（官方）写的样本 | 本机没有 .NET/Mono | 在装了 KeePass 的机器上生成后登记 |
| 移动端客户端（KeePassDX、KeePassium、Strongbox）写的样本 | 需要真机或模拟器 | K003 前后在测试机上生成 |
| KeeAgent 本体读取验证、带口令的 SSH 私钥 | 没有 KeePass/KeeAgent；加密 OpenSSH 私钥需要 bcrypt 库 | KeeAgent 设置目前按格式手写，只验证了字节保留 |
| 其余 4.x 参数/资源组合 | 已新增 278 案，包含 AES-KDF 下 4.0/4.1、AES/ChaCha20 的认证后 gzip/XML 攻击；详见 K002_RESOURCES | 后续补其它 KDF/参数、候选 writer、模糊测试和设备预算，不把当前范围外推 |
