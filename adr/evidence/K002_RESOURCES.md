# K002 增量证据：4.x 认证负载与资源边界

日期：2026-10-19。续接 K002/K069 合成准备。K001/K002/K068 保持 REVIEW，K069 保持 DOING；K003–K067、K070–K089 为 TODO。独立人工复核和生产写入门槛仍待完成。

## 交付与输入

新增 [v4_payload.py](../../tests/fixtures/kdbx/v4_payload.py)、[278 案配方清单](../../tests/fixtures/kdbx/v4_payload_manifest.json) 和 [26 项测试](../../tests/kdbx_oracle/tests/test_v4_payload.py)。使用已登记的 G40-RICH、G41-RICH，均源自 KeePassXC 2.7.12；进入解码前校验固定 ID 与 SHA-256，拒绝任意路径或变化的源文件。公开合成密码与完整输入哈希在清单中。

4.0/4.1 × AES/ChaCha20 × gzip/不压缩共有 8 个正例。留存四份不压缩 KDBX，共 553361 字节，其余正例及 270 个负例现场重建、核对清单哈希。当前共有 82 份留存 KDBX；此前 78 份字节保留。新文件属于认证变异工具输出，来源不能标成“参考客户端写的不压缩库”。

| 留存文件 | 字节 |
| --- | ---: |
| v40-rich-aes-uncompressed.kdbx | 137867 |
| v40-rich-chacha20-uncompressed.kdbx | 137852 |
| v41-rich-aes-uncompressed.kdbx | 138827 |
| v41-rich-chacha20-uncompressed.kdbx | 138815 |

本批复用 cryptography 46.0.4、Python 3.12.12 与标准库 zlib；编译/运行时 zlib 均为 1.2.12。清单记录实际版本和参与生成/验证的源码哈希，没有新增依赖或安装工具链。既有依赖版本、许可和替换边界见 [K002_LIBRARIES](K002_LIBRARIES.md)。

## 认证层与测试层次

按 [官方完整 KDBX 4.1 规范](https://keepass.info/help/kb/kdbx.html)，内层头部和 XML 共同经过可选 gzip，再加密，最后进入 HMAC 分块；每块认证覆盖隐式序号、长度与密文，空结束块也认证。4.0 的相关封装背景见 [KDBX 4 变更规范](https://keepass.info/help/kb/kdbx_4.html)。

变异工具保留源内层头和受保护 XML 字节，只在指定用例替换负载；使用已有 AES/ChaCha20 原语重新加密，并重算头部 SHA/HMAC、数据块及结束块 HMAC。测试另按最终字节独立重算 MAC，不调用工具的 block_mac/frames 或 reader 的认证函数。其 hmac_base 仍来自登记源的派生结果；这不是另一套完整独立解码器，八个安全正例由 KeePassXC 交叉读取补充验证。

| 目标层 | 案例数 | 主要覆盖 |
| --- | ---: | --- |
| 完整正例 | 8 | 两个版本、两种外层密码、压缩/不压缩 |
| HMAC | 48 | 后续块/结束块损坏、块交换/重复/删除、长度异常、缺失/截断结束块、尾随/双结束块 |
| gzip | 32 | CRC、ISIZE、非法 DEFLATE、截断、拼接 member、尾随数据、XML/内层附件解压预算 |
| 内层头部 | 104 | 长度、缺失项、未知字段、附件无 flags、重复/冲突流配置、非空结束字段 |
| XML | 56 | DOCTYPE、外部实体声明、延迟 DOCTYPE、UTF-16、深度、畸形 XML、错误根 |
| 受保护值编码 | 16 | 非法 base64 字符、非 ASCII 内容 |
| 未支持内层流 | 8 | 完整合法结构中的未知算法编号 |
| AES 填充 | 2 | 认证正确但末尾 padding 字节为 0 |
| AES 密文长度 | 4 | 认证正确的非对齐密文、空密文 |
| 合计 | 278 | 8 个正例、270 个负例；不是 278 个 unittest 方法 |

负例同时检查异常类型、原因片段、实际目标函数被调用及后续函数未调用。所有 HMAC 失败均在解密/解压前拒绝；gzip 失败不进入内层头或 XML；DOCTYPE/UTF-16 不调用 ElementTree 解析器。外部实体只包含 synthetic.invalid 声明，不发起请求，也不交给外部 CLI 执行。

额外边界用例验证 XML 深度 256 可读、257 拒绝；HMAC 块可为 17、4093、1 MiB，以及小负载的 1 字节，允许在 AES 密文块中间划分。还验证错误密码先于负载处理、未登记输入先于解密被拒绝。

## 实际缺陷与修复

修复前，选定的 8 个测试方法出现 40 个失败、28 个异常子案例，session d56f991f-8bbc-43ad-9132-86f24810ff72。更早无 mock 探针确认 AES/ChaCha20 都能打开重复配置/非空结束字段，并直接漏出坏 gzip 的 zlib.error，session bcca3be9-528a-4a4d-92de-c70f52aeb1e6。

- gzip 的 CRC/ISIZE/DEFLATE 错误现统一为 KdbxIntegrityError，预算、截断和多余数据原有判断保持。
- 重复的内层流 ID/密钥配置和非空结束字段现明确拒绝，避免后值覆盖或丢弃数据；多个附件仍合法累加。这是本 oracle 的读取策略。当前完整规范没有明示流配置必须唯一，结束字段值用的是 should be empty，不能把本策略描述成规范逐字强制。
- XML base64 错误现统一为 KdbxFormatError，消息不包含输入值；保留原 validate=True 行为、空值规则及保护流顺序。补充受保护字段、明文 XML 附件池、4.1 容器里的旧式 Meta/Binaries，以及真正的 3.1 HeaderHash 非法 base64 端到端回归。

这批修复没有改变受支持算法、KDF 参数、语义忽略规则或源数据。reader 接近 800 行，但改动仍局限于现有三个处理点与一个小型错误转换函数，本轮未另作结构重构。

## 资源预算的准确含义

负例有 4 MiB 的可压缩填充，测试将读取预算降为 256 KiB；无需真的分配默认最大 256 MiB。两个 gzip 炸弹分别把填充放进 XML 和内层附件，证明限制覆盖整个解压结果。

4.x gzip 分支的 max_xml_bytes 限制的是内层头部加 XML 的总解压长度；不压缩分支限制 XML 本身，另受全文件 64 MiB 上限约束。两条路径都实测“恰好上限通过、少一个字节预算拒绝”。本轮保留这个既有接口含义，没有把它包装成统一生产内存预算。XML 深度在构树后检查；仍无生产取消、超时、设备内存或 Web 预算结论。

## 保留与交叉读取

八个正例与原输入的完整解码 XML 字节、附件池字典逐项一致，语义比较不添加忽略项；当前/历史受保护值、附件字节、保护标志和 XML 顺序保留。两个源各有两条历史，已核对已知合成当前口令及仅存在于历史中的受保护值。

KeePassXC 2.7.12 重新打开八个安全正例，其全部当前/历史字段和保护标记一致。CLI 的 4.x XML 导出没有完整附件池，附件结论来自 oracle 对源和输出的逐字比较，未冒充 CLI 附件导出证据。

旧 Rust 清单只更新当前 reader 分析 SHA，并追加 verification_revisions 指向本页；generation_provenance、生成二进制哈希、原生成会话及 12 份 KDBX 均保留。测试固定当前相对原生成仅有 generator 和 reader 两个文件变化，修订链保留旧 reader SHA。旧参考输出的 9 条原始差异、3 条额外差异及 lossless_roundtrip=false 不变。

## 生成、失败与验证

首次构造原型曾漏掉外层结束字段，正控制立即报头部截断；修复后才进行本批登记，没有留存错误产物。随后生成前 21 项端到端/边界/CLI 检查通过，session 53621b27-f4c2-4c7b-9299-b7f03e3352df；首次登记 session b0bf715e-2d48-423a-a5b5-469777d071d7。

| 已执行分项 | 结果 |
| --- | --- |
| 新增完整测试 | 26 项，16.431 秒，无跳过；e73be710-0a96-4d64-a1e7-15e9b5c720c1 |
| 旧 Rust 参考回归 | 15 项，5.126 秒，无跳过；b480e2ff-6613-4080-82b2-d4f974f453cc |
| 模型只读复核 | review_kdbx4_resources 核对封装、MAC、负载到达、AES 填充、清理、追溯及 reader 修复；不替代独立人工批准 |

生成器先构造全部字节，已有清单只核对配方/产物哈希，成功重跑不写入。首次留存使用排他创建、0600 和 fsync；普通异常仅清理本次新建文件。测试覆盖重复执行、已有输出/陈旧清单拒绝、清单创建异常与无关文件保留。首次生成并不代替失败行为测试，应使用以下统一入口验收。

没有实测磁盘写满、fsync 故障或进程强杀；逐文件发布不构成跨文件原子事务。强杀可能留下未登记输出，下次拒绝覆盖，不自动恢复。

最终文件版本完成后运行：

~~~sh
python3 -B tests/run_python_tests.py --suite oracle
python3 -B tests/run_python_tests.py --suite domain
python3 -B tests/fixtures/kdbx/v4_payload.py
python3 -B tests/reference_writer/generate.py
python3 -B tests/fixtures/kdbx/matrix_generate.py
python3 -B adr/design/verify.py
python3 -B adr/design/verify_ios.py
python3 -B adr/verify_personal_vault.py
git diff --check
~~~

当前入口为 131 项 oracle 加 93 项领域，共 224 项。完整回归和无后续文件写入的验收会话由任务 f26e346131e148b29624e5712db03028 保存；上批 198 项、旧 10k 时间/RSS 属于历史结果，本批没有新增性能量测。

## 后续边界与回滚

继续补固定版本官方 KeePass/KeeAgent/移动客户端、未覆盖 KDF/压缩/算法参数组合、自动秘密扫描和真机/Web 资源证据。4.x 资源攻击已覆盖本页列明组合，不等于全部算法/KDF、模糊测试或候选 writer 故障矩阵通过。K003 双候选、跨客户端再编辑、生产会话/事务保存/取消/恢复及人工门槛仍按计划推进。

回滚仅撤销本页列明的 helper、清单、四份新文件、26 项新测试、reader 局部修复、旧 Rust 当前验证修订及对应文档/精确忽略项；保留此前样本和原生成追溯，不重置整仓库。全程只使用公开合成资料，没有真实库、账号、外部发布、commit 或 push。
