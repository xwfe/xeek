# kdbxweb 上游公开测试原件

固定来源：keeweb/kdbxweb，提交 7601e45d2a437f35a7fa3d767164eab60bc05d42。这里只保留三份公开 KDBX 测试文件、demo.key 和原始 MIT LICENSE，不安装或执行 kdbxweb 实现代码。原件来源 URL、Git blob SHA-1、原字节 SHA-256、参数与公开凭据见 [manifest.json](manifest.json)。

| 文件 | 只读覆盖 |
| --- | --- |
| Argon2id.kdbx | KDBX 4.0、AES-256-CBC、Argon2id |
| AesChaCha.kdbx | KDBX 3.1、外层 ChaCha20、AES-KDF |
| Argon2ChaCha.kdbx | KDBX 4.0、外层 ChaCha20、Argon2d；现由 oracle 完整解码并与参考 CLI 交叉读通过 |

公开密码为 demo，三个文件都同时需要 demo.key。具体生成 writer/version 未证实；Meta/Generator 不代替来源版本证据。上游原件中的历史示例 URL 和命令模板仅作保留/解析数据，不访问、不执行、不注册凭据。密钥文件保留 CRLF，全部原件保持原哈希。

从仓库根目录执行（入口自动加载固定的项目内 Argon2 依赖）：

~~~sh
python3 -B tests/run_python_tests.py --suite oracle --pattern test_upstream.py
~~~

九项检查覆盖固定哈希、实际解码参数、原字段/历史、上游公布的附件哈希、错误凭据、密文损坏和 KeePassXC 交叉读取。4.x CLI 导出缺少附件池，不能替代附件内容检查。来源与首轮失败记录见 [K002_ALGORITHMS](../../../../adr/evidence/K002_ALGORITHMS.md)，当前 Argon2d 接入与剩余范围见 [K002_LIBRARIES](../../../../adr/evidence/K002_LIBRARIES.md)。原始 KDBX/key/LICENSE 哈希保留，清单另记接入前 oracle 状态。

