# kdbx_oracle：KDBX 测试对照工具

只读的 KDBX 解码器和语义比较器，给 K002 样本和 K003 无损测试当“独立裁判”。**不是 keex 的生产实现，不写 KDBX，只用于合成数据**——真实密码库不要交给它（[真实数据规则](../../adr/REAL_DATA_RULES.md)）。

## 怎么跑

需要 Python 3.12 和 `cryptography`（本机已有 46.0.4，没有为此新装任何东西）。在本目录下：

```sh
python3 -m unittest discover -s tests -v
```

在别的目录跑会报 `Start directory is not importable`，先 `cd tests/kdbx_oracle`。

## 为什么要自己读，不用 KeePassXC

K003 要判断候选库有没有丢数据。如果用 KeePassXC 读两边的文件，KeePassXC 读取时自己丢掉的东西两边都看不见，结论会是假的“无损”。实测 KeePassXC 2.7.12 导入 XML 时就会丢掉 CustomData 条目上的 `LastModificationTime`，并把标签 `合成;synthetic` 重排成 `synthetic,合成`。

## 支持范围

| 项 | 支持 | 说明 |
| --- | --- | --- |
| 格式 | KDBX 3.x、4.0、4.1 | 高于 4.1 直接拒绝 |
| 密钥 | 密码、密钥文件（XML 1.0/2.0、32 字节、64 位十六进制、其他文件取 SHA-256）、两者组合 | |
| KDF | AES-KDF、Argon2id | **Argon2d 不支持**：cryptography 只有 Argon2id。KeePassXC 图形界面默认就是 Argon2d，这是已知缺口 |
| 外层加密 | AES-256-CBC、ChaCha20 | Twofish 不支持 |
| 内层保护流 | Salsa20（自写，见 `salsa20.py`）、ChaCha20 | ArcFour 不支持 |
| 完整性 | 4.x 头部 SHA-256 + 头部 HMAC + 分块 HMAC，拒绝结束块后的多余数据；3.x StreamStartBytes + 块哈希 + HeaderHash | 3.x 的 HeaderHash 不符就拒绝；缺失时 `header_hash == "missing"`，调用方应只读（[威胁模型](../../adr/THREAT_MODEL.md) T1） |

**没有被样本覆盖到的路径**：ChaCha20 外层加密、Argon2id。keepassxc-cli 不能选算法，只会写 AES-256 + AES-KDF，所以这两条代码路径目前没有端到端验证。

## 错误类型

| 异常 | 意思 |
| --- | --- |
| `KdbxKeyError` | 密钥错误，或头部/密文被改——这一步在格式上分不出是哪种 |
| `KdbxIntegrityError` | 密钥对，但内容被改、被截断或有多余数据 |
| `KdbxFormatError` | 不是 KDBX、字段缺失、长度不对 |
| `KdbxUnsupported` | 合法但本工具不支持，或超过测试上限 |
