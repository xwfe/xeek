# kdbx_oracle：KDBX 测试对照工具

只读的 KDBX 解码器和语义比较器，给 K002 样本和 K003 无损测试当“独立裁判”。**不是 keex 的生产实现，不写 KDBX，只用于合成数据**——真实密码库不要交给它（[真实数据规则](../../adr/REAL_DATA_RULES.md)）。

## 怎么跑

需要 Python 3.12 和 `cryptography`（本机已有 46.0.4，没有为此新装任何东西）。在本目录下：

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

不报：加密随机数、二进制池编号（附件按内容 SHA-256 比）、时间的 3.1/4.x 两种写法、String/Binary/CustomData 的先后顺序、非用户字段里的 `true`/`True`、标签的顺序和分隔符、空元素和不写该元素、值为空的五个标准字段和不写该字段。自定义字段哪怕值为空，有和没有也算不同。

其余都报：不认识的元素和属性、保护标记变化、分组和条目的排列顺序、历史（按位置比较）。哪些差异是“改了就该变”的，由测试自己用 `--ignore` 列出来，比较器不替人猜。路径写法见 `kdbx_oracle/semantic.py` 开头。

## 为什么要自己读，不用 KeePassXC

K003 要判断候选库有没有丢数据。如果用 KeePassXC 读两边的文件，KeePassXC 读取时自己丢掉的东西两边都看不见，结论会是假的“无损”。KeePassXC 2.7.12 实际会丢什么、改什么，见[样本说明](../fixtures/kdbx/README.md)里的“KeePassXC 2.7.12 写库时自己改了什么”。

## 支持范围

| 项 | 支持 | 说明 |
| --- | --- | --- |
| 格式 | KDBX 3.x、4.0、4.1 | 高于 4.1 直接拒绝 |
| 密钥 | 密码、密钥文件（XML 1.0/2.0、32 字节、64 位十六进制、其他文件取 SHA-256）、两者组合 | |
| KDF | AES-KDF、Argon2id | **Argon2d 不支持**：cryptography 只有 Argon2id。KeePassXC 图形界面默认就是 Argon2d，这是已知缺口 |
| 外层加密 | AES-256-CBC、ChaCha20 | Twofish 不支持 |
| 内层保护流 | Salsa20（自写，见 `salsa20.py`）、ChaCha20 | ArcFour 不支持 |
| 资源上限 | 解压/XML 256 MiB（`read_kdbx(max_xml_bytes=...)` 可调小）、XML 嵌套 256 层、AES-KDF 2^32 轮、Argon2 1 GiB / 65536 次、文件 64 MiB；任何位置出现 DOCTYPE/ENTITY 就拒绝 | 只防测试被卡死，不是 keex 的资源策略（K015） |
| 完整性 | 4.x 头部 SHA-256 + 头部 HMAC + 分块 HMAC，拒绝结束块后的多余数据；3.x StreamStartBytes + 块哈希 + HeaderHash | 3.x 的 HeaderHash 不符就拒绝；缺失时 `header_hash == "missing"`，调用方应只读（[威胁模型](../../adr/THREAT_MODEL.md) T1） |

**没有被样本覆盖到的路径**：ChaCha20 外层加密、Argon2id。keepassxc-cli 不能选算法，只会写 AES-256 + AES-KDF，所以这两条代码路径目前没有端到端验证。

## 错误类型

| 异常 | 意思 |
| --- | --- |
| `KdbxKeyError` | 密钥错误，或头部/密文被改——这一步在格式上分不出是哪种 |
| `KdbxIntegrityError` | 密钥对，但内容被改、被截断或有多余数据 |
| `KdbxFormatError` | 不是 KDBX、字段缺失、长度不对 |
| `KdbxUnsupported` | 合法但本工具不支持，或超过测试上限 |
