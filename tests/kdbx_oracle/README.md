# kdbx_oracle：KDBX 测试对照工具

只读的 KDBX 解码器和语义比较器，给 K002 样本和 K003 无损测试当“独立裁判”。**不是 keex 的生产实现，不写 KDBX，只用于合成数据**——真实密码库不要交给它（[真实数据规则](../../adr/REAL_DATA_RULES.md)）。

## 怎么跑

需要 Python 3.12 和 `cryptography`（版本见 `requirements.txt`）。装了 `keepassxc-cli` 会多跑一组和 KeePassXC 导出的对照，没装就跳过。在本目录下：

```sh
python3 -m unittest discover -s tests -v
```

在别的目录跑会报 `Start directory is not importable`，先 `cd tests/kdbx_oracle`。

看一个库的结构摘要、比较两个库（同样在本目录下）：

```sh
KX_PW='合成密码' python3 -m kdbx_oracle summary --password-env KX_PW 库.kdbx
KX_PW='合成密码' python3 -m kdbx_oracle diff --password-env KX_PW A.kdbx B.kdbx \
    --ignore '*KPXC_RANDOM_SLUG*' --ignore '*_LAST_MODIFIED*'
```

- 密码只读环境变量或提示输入，不接受命令行参数——参数会进 shell 历史和 `ps`。密钥文件用 `--keyfile`，只用密钥文件时加 `--no-password`；B 库密钥不同就用 `--b-keyfile` / `--b-password-env`。
- `summary` 只输出计数、字段名和附件 SHA-256，不输出任何字段值。
- `diff` 退出码：0 无差异，1 有差异，2 打不开。受保护值默认只报长度，`--reveal` 才显示内容，只对合成样本用。
- 上面两个 `--ignore` 是 KeePassXC 每次保存都会变的自有元数据；不加的话，同一份内容被 KeePassXC 存一遍也会报 3–4 条差异。

## 比较器认为什么算“一样”

完整规则只写在 `kdbx_oracle/semantic.py` 开头。要点：加密随机数、附件池编号、时间写法、字段先后、标签顺序、**已知**的空元素这类只影响字节的东西不报；不认识的元素（哪怕是空的）、保护标记、分组和条目顺序、历史都报。附件内容和附件保护标记分开报（manifest 里是 `changed/value` 和 `changed/attrs`）。哪些差异是“改了就该变”的，由测试自己用 `--ignore` 列出来，比较器不替人猜。

## 为什么要自己读，不用 KeePassXC

K003 要判断候选库有没有丢数据。如果用 KeePassXC 读两边的文件，KeePassXC 读取时自己丢掉的东西两边都看不见，结论会是假的“无损”。KeePassXC 2.7.12 实际会丢什么、改什么，见[样本说明](../fixtures/kdbx/README.md)里的“KeePassXC 2.7.12 写库时自己改了什么”。

## 实现了哪些

下表是代码里有的路径。**有代码不等于验证过**：哪些路径有样本覆盖、哪些没有，只看[样本说明](../fixtures/kdbx/README.md)末尾的缺口表。

| 项 | 实现 | 说明 |
| --- | --- | --- |
| 格式 | KDBX 3.x、4.0、4.1 | 高于 4.1 直接拒绝 |
| 密钥 | 密码、密钥文件、两者组合 | 密钥文件按 KeePassXC 2.7.12 `FileKey.cpp` 的顺序判定：XML（1.0 base64、2.0 十六进制且必须有 Hash）→ 恰好 32 字节 → 恰好 64 个十六进制字符 → 整个文件取 SHA-256。含 DOCTYPE 或非 UTF-8 的文件不当 XML 解析，这是和 KeePassXC 唯一的差别 |
| KDF | AES-KDF、Argon2id | **Argon2d 不支持**：cryptography 只有 Argon2id。KeePassXC 图形界面默认就是 Argon2d |
| 外层加密 | AES-256-CBC、ChaCha20 | Twofish 不支持（KeePass 2.x 里是插件，KeePassXC 原生支持） |
| 压缩 | gzip、不压缩 | |
| 内层保护流 | Salsa20（自写，见 `salsa20.py`）、ChaCha20 | ArcFour 不支持 |
| XML | 只收 UTF-8；任何位置出现 DOCTYPE/ENTITY 就拒绝 | UTF-16 的 DOCTYPE 按 UTF-8 字节搜不到、却会被 expat 展开，所以先卡编码；KeePass 只写 UTF-8 |
| 资源上限 | 解压/XML 256 MiB（`read_kdbx(max_xml_bytes=...)` 可调小）、XML 嵌套 256 层、AES-KDF 2^32 轮、Argon2 1 GiB / 65536 次、文件 64 MiB | 只防测试被卡死，不是 keex 的资源策略（K015） |
| 完整性 | 4.x 头部 SHA-256 + 头部 HMAC + 分块 HMAC，拒绝结束块后的多余数据；3.x StreamStartBytes + 填充 + 块哈希 + HeaderHash | 3.x 先比 StreamStartBytes 再去填充，所以截断报“文件坏了”而不是“密码错”。HeaderHash 不符就拒绝；缺失时 `header_hash == "missing"`，调用方应只读（[威胁模型](../../adr/THREAT_MODEL.md) T1） |

## 错误类型

| 异常 | 意思 |
| --- | --- |
| `KdbxKeyError` | 密钥错误，或头部/密文被改——这一步在格式上分不出是哪种 |
| `KdbxIntegrityError` | 密钥对，但内容被改、被截断或有多余数据 |
| `KdbxFormatError` | 不是 KDBX、字段缺失、长度不对 |
| `KdbxUnsupported` | 合法但本工具不支持，或超过测试上限 |

## 依赖登记

AGENTS.md 要求新增第三方库登记下面四项。两个依赖都只用在测试里，不进 keex 产品。

| 依赖 | 许可证 | 固定版本 | 维护情况 | 替换边界 |
| --- | --- | --- | --- | --- |
| [cryptography](https://github.com/pyca/cryptography)（Python 库） | Apache-2.0 OR BSD-3-Clause | 46.0.4，见 `requirements.txt` | PyCA 维护，持续发版；本机本来就装着，没有为此新装 | 只用 AES-CBC、ChaCha20、Argon2id、PKCS7、以及测试里读回 Ed25519/P-256 密钥。换成任何提供这些原语的库都只动 `reader.py` 和 `tests/fixtures/kdbx/source.py` |
| keepassxc-cli（外部程序） | GPL-2.0/3.0 | 2.7.12（样本就是用它生成的） | KeePassXC 项目持续发版 | 只当外部程序调用来生成样本和做对照，不链接、不复制它的代码；没装时对照测试跳过，重新生成样本不可用 |
