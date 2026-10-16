# K002 合成 KDBX 样本

这里的 `.kdbx`、`.keyx`、`.key` 全是合成数据，密码和密钥公开写在 `manifest.json` 里，只用于测试。里面的 SSH 私钥和 Passkey 私钥从公开种子派生，**绝不能**加进任何 `authorized_keys` 或注册到任何网站。

## 怎么用

- 每个样本的密码、密钥文件、SHA-256、预期结果和结构摘要都在 `manifest.json`。摘要由 [kdbx_oracle](../../kdbx_oracle/README.md) 算出，不含字段值。
- 回归测试：`cd tests/kdbx_oracle && python3 -m unittest discover -s tests`，会核对文件哈希、摘要、KeePassXC 的写入差异和关键明文值，本机约 3.5 秒。
- 给 keex 自己的测试（K003 起）用时，以 manifest 里的 `expect` 为准，用 `kdbx_oracle diff` 对比语义。

## 怎么重新生成

```sh
python3 -I tests/fixtures/kdbx/generate.py                 # 只补还不存在的样本
python3 -I tests/fixtures/kdbx/generate.py --only G41-RICH --force   # 重做指定样本
```

需要 `keepassxc-cli`（现有样本用 2.7.12 生成）和 Python `cryptography`。**重做一定会改变文件字节**（KeePassXC 每次随机生成种子和 IV），提交前要说明原因；用别的 KeePassXC 版本重做时，`writer_changes` 可能变，那本身就是要记录的兼容性信息。

`*.kdbx`、`*.keyx`、`*.key` 在 `.gitignore` 里，新样本要逐个 `git add -f`。

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
| G31-KEYBIN | 3.1 | cli-keyfile | 密码 + 64 字节二进制密钥文件 | 密钥文件取 SHA-256 的路径 |
| G31-KEYHEX | 3.1 | cli-keyfile | 密码 + 64 位十六进制密钥文件 | 密钥文件直接当 32 字节密钥的路径 |

错误密码、缺少密钥文件不单独存文件，测试里对每个样本动态验证。

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
| Argon2d / Argon2id KDF、ChaCha20 外层加密、不压缩 | keepassxc-cli 不能选算法，只写 AES-256 + AES-KDF + gzip；kdbx_oracle 也不支持 Argon2d | 用 KeePassXC 图形界面手工生成并登记，或经批准引入带 Argon2d 的库 |
| KeePass 2.x（官方）写的样本 | 本机没有 .NET/Mono | 在装了 KeePass 的机器上生成后登记 |
| 移动端客户端（KeePassDX、KeePassium、Strongbox）写的样本 | 需要真机或模拟器 | K003 前后在测试机上生成 |
| KeeAgent 本体读取验证、带口令的 SSH 私钥 | 没有 KeePass/KeeAgent；加密 OpenSSH 私钥需要 bcrypt 库 | KeeAgent 设置目前按格式手写，只验证了字节保留 |
| 损坏、截断、尾部污染、HeaderHash、超大参数、压缩炸弹、XML 攻击样本 | K002 下一步 | 由黄金样本确定性变异生成 |
