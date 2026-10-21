# K002 增量证据：上游公开算法测试原件

日期：2026-10-19。K002 保持 REVIEW。本页保存固定上游原件的来源与首轮执行记录；随后接入成熟 Argon2 库和 Rust 参考实验的当前结果见 [K002_LIBRARIES](K002_LIBRARIES.md)。没有安装或执行 kdbxweb 实现，不把读取成功当成生产写入认证。

## 当前补充：Argon2d 已接通

Argon2ChaCha.kdbx 现由 oracle 完整解码，实际执行 KDBX 4.0 / 外层 ChaCha20 / Argon2d v19 路径；原参数 24576 字节、2 次、并行 3 保留。当前三个原件的字段、历史、附件摘要、错误凭据/密文损坏和 CLI 交叉读均通过，九项测试 0.223 秒，session a70c6e98-9c44-469d-9052-75069f6affaa。原始文件、许可证与来源哈希没有重写；来源清单保留接入前 oracle 状态。原 writer/version 仍未知，新增已知 Rust helper 不改变这些原件的来源结论。

## 固定来源与许可

来源为 [keeweb/kdbxweb](https://github.com/keeweb/kdbxweb/tree/7601e45d2a437f35a7fa3d767164eab60bc05d42) 的固定提交 7601e45d2a437f35a7fa3d767164eab60bc05d42。五个原件保存在 [upstream_kdbxweb](../../tests/fixtures/kdbx/upstream_kdbxweb/README.md)，包括三份 KDBX、demo.key 和完整 MIT LICENSE。每个文件均验证 Git blob SHA-1，另算原始字节 SHA-256；精确 URL、长度和哈希见 [manifest.json](../../tests/fixtures/kdbx/upstream_kdbxweb/manifest.json)。

公开密码 demo 配合 demo.key，直接来自固定提交的 [kdbx.spec.ts](https://github.com/keeweb/kdbxweb/blob/7601e45d2a437f35a7fa3d767164eab60bc05d42/test/format/kdbx.spec.ts) 相应测试；checkDb 同时给出示例字段、历史和附件内容哈希。密钥文件 CRLF 原字节和许可证均保留。没有复制或执行上游实现代码，因此没有新增运行时依赖。

这些是上游长期公开的测试原件，含上游历史示例 URL 与 AutoType/OverrideURL 文本；本轮只解析字段，从不访问 URL、执行命令、注册凭据或连接账号。keex 自行生成的数据继续采用公开种子和保留域名。

生成这些原件的具体 writer/version 未证实，在清单中保持 null。Argon2id 文件的 Meta/Generator 自报 KeePass，只能作为容器元数据记录，不能据此声明某一版 KeePass 已实测。上游来源增加了测试输入来源，不补齐有明确版本的多 writer 往返矩阵。

## 接入 Argon2d 前的首轮结果（历史）

| 原件 | 格式 / 外层加密 | KDF 原参数 | oracle | KeePassXC 2.7.12 |
| --- | --- | --- | --- | --- |
| Argon2id.kdbx，3973 字节 | 4.0 / AES-256-CBC | Argon2id v19；8192 字节、3 次、并行 1 | 解锁、HMAC、内层流、字段/历史/附件摘要通过 | 只读导出成功，原字段和历史一致 |
| AesChaCha.kdbx，3877 字节 | 3.1 / ChaCha20 | AES-KDF 6000 轮 | 解锁、块哈希及 HeaderHash 通过 | 只读导出成功，原字段和历史一致 |
| Argon2ChaCha.kdbx，3960 字节 | 4.0 / ChaCha20 | Argon2d v19；24576 字节、2 次、并行 3 | 明确返回 Argon2d unsupported | 独立解锁成功，公开示例字段/历史一致 |

这些很小的 KDF 参数只是上游算法夹具，不是生产推荐、参数校准或高成本资源验证。首轮当时未覆盖 oracle 的 Argon2d，也不能用第三行证明它已经执行了 4.x 外层 ChaCha20 解密路径。

首轮当时的两个可解码原件均有 8 个分组、4 个当前条目、2 个历史、1 个删除对象、1 份 15 字节附件。附件 SHA-256 与上游 checkDb 的公开预期一致。错误密码、错误密钥文件和密文损坏均拒绝。三个原件在 CLI 导出前后字节完全不变。

## 测试及一次失败

新增 [test_upstream.py](../../tests/kdbx_oracle/tests/test_upstream.py)，九项：

~~~sh
cd tests/kdbx_oracle
python3 -B -m unittest discover -s tests -p test_upstream.py
~~~

首次 8 项通过、1 项失败，session 767dd135-f33a-462b-bff4-ca78214b46d7：CLI 导出给一个原本缺省 Notes 的条目补了空字段，而测试要求完整 map 直接相等。

修正后原字段仍逐项比较值与保护位；新增项仅允许五个标准字段的空默认值，密码默认保护，其他默认不保护。自定义字段、新非空值和原字段保护变化不放行。随后九项通过，0.138 秒，session 96987b0d-0a2b-4ff3-8739-d9c3f5e30908。

4.x 的 CLI XML 导出没有完整附件池，因此字段交叉读与附件验证分开；不能将 CLI 成功表述为独立逐字导出附件。全部 oracle 入口现为 66 项，最终统一执行由本轮任务验收会话记录。

## 首轮为什么采用现成原件

首轮环境中没有 argon2 / pykeepass 包、KeePass 或 Mono。KeePassXC CLI db-edit 帮助及固定 [2.7.12 官方源码](https://github.com/keepassxreboot/keepassxc/tree/2.7.12/src/cli) 的 DatabaseCreate、Import、DatabaseEdit 只暴露密码、密钥文件、当前 KDF 的解锁时间校准，没有选择外层 cipher/KDF 的入口。

algorithm_feasibility 子代理只读核对官方源码与上游公开原件；主会话独立取回固定版本、验证 blob、执行解锁与测试。没有用安装环境或自行实现 writer 绕过缺口，也没有把模型资料审查当人工独立审批。

首轮留下的 Argon2d 读取缺口已由 [K002_LIBRARIES](K002_LIBRARIES.md) 补充。当前仍保留未支持参数、官方/移动参考客户端、保存互通与资源/安全门槛；同 RP 与 1k/10k 增量见 [K069_MATRIX](K069_MATRIX.md)。本页五个原件的回滚仅涉及来源清单/说明、新测试与精确忽略规则，不改旧黄金文件。

