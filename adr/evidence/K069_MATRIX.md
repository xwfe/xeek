# K069 增量证据：同 RP 多凭据与 1k/10k 规模矩阵

日期：2026-10-19。属于 K002/K069 的公开合成准备；主状态仍为 K069 DOING，K002/K068 REVIEW。原 37 份 K002 和 9 份领域库、两份原清单均保留，不重新生成。

本页是成熟依赖接入前那一批的执行记录，159 项与资源量测保留原结果；当前 Argon2d 和固定 Rust 参考保存的新增实现、差异及依赖见 [K002_LIBRARIES](K002_LIBRARIES.md)。

## 交付

- [matrix_source.py](../../tests/fixtures/kdbx/matrix_source.py)：确定性源 XML，复用固定 source.py / vault_source.py。
- [matrix_generate.py](../../tests/fixtures/kdbx/matrix_generate.py)：已有 KeePassXC 2.7.12 导入、复制后编辑、校验、排他发布。
- [matrix_checks.py](../../tests/fixtures/kdbx/matrix_checks.py)：源字段、首次导入差异、相邻保存和历史快照检查。
- [matrix_probe.py](../../tests/fixtures/kdbx/matrix_probe.py)：单独进程测量 CLI 与只读解码/领域检查。
- [matrix_manifest.json](../../tests/fixtures/kdbx/matrix_manifest.json)：7 案、17 份新增 KDBX，共 33177180 字节；完整源/文件哈希、参数、摘要、各阶段原始和筛选后差异、资源原始读数。
- [test_matrix.py](../../tests/vault_domain/test_matrix.py) 与 [test_matrix_generation.py](../../tests/vault_domain/test_matrix_generation.py)：15 项内容/损坏测试和 3 项生成守卫测试。

生成环境为 macOS arm64、Python 3.12.12、cryptography 46.0.4、KeePassXC CLI 2.7.12。17 份均为 AES-256-CBC、AES-KDF 1000000 轮，没有为规模测试降低参数。原始生成版本在 generation_provenance 中；provenance 是当前验证版本。生成后只修正生成器失败清理范围的 docstring，没有改执行语句、XML、二进制、差异或量测结果。

## 同一 RP 的三个现代 Passkey

KDBX 3.1、4.0、4.1 各执行 import → edit1 → edit2，共九份新增小库，每份 39 个当前条目。保留原有另一个 RP 的旧字段名 Passkey。

| 凭据 | 用户身份 | 凭据 ID / P-256 密钥 | 父登录条目 |
| --- | --- | --- | --- |
| 原 A | synthetic-user、handle A | A | 原合成服务账户 |
| 新 B | synthetic-user-b、handle B | B，独立于 A | 新增合成第二账户 |
| A 的第二把 | 与 A 相同的用户名和 handle | C，独立于 A/B | 与 A 相同 |

三者使用精确 RP ID passkey.example.com；Entry UUID、credential ID、公钥各不相同。PEM 能由现有 cryptography 解析，私钥、user handle 和 parent 别名的保护位保留。编辑只改原 A 的普通 UserName；KPEX_PASSKEY_USERNAME 等原字段不随之改写。两次新增历史分别等于保存前快照，私钥与未知字段不会错配。

首次导入仍有旧参考客户端的已知变化：分组 IconID、4.x 附件保护位、4.1 两个 CustomData 时间丢失等，精确路径保留在清单。没有把这些变化重定义为正确源数据。

本项证明编码、身份区分和保存保留；没有注册到网站、调用系统提供者或完成跨端登录。

## 规模与附件

每块 25 个当前条目，包含 13 类资料、负例和一条回收站记录。40/400 块分别精确得到 1000/10000 个当前条目，数量包含回收站，历史另计。UUID、动态关系/规则/事件 ID、旧 hex parent、JSON target、ruleId、targetEventId、basisEventId 和 evidence.entry 一起重映射。旧 parent 映射只针对这份确定源中的规范 hex，不是通用迁移器。

| 当前条目 | 回收站条目 | 历史：导入 → 编辑后 | 关系 | 规则 | 事件 | 当前 / 历史附件引用 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1000 | 40 | 40 → 41 | 920 | 40 | 80 | 161 / 1 |
| 10000 | 400 | 400 → 401 | 9200 | 400 | 800 | 1601 / 1 |

每种条目数量各生成小/大附件两案，只使用 KDBX 4.1；每案 import → edit1，因此规模部分共八份 KDBX。

小附件池为 8253 字节；大附件池为 4198461 字节。两者都只有三份唯一内容：61 字节证明文本、4096 字节 shared、4096 字节或 4 MiB 的独立 payload。大块由公开固定种子生成，不依赖易压缩的重复零；第 0 块旧卡的当前/历史共用它。条目引用增长不冒充唯一附件字节增长。

所有原当前/历史附件逐字比对，检查池保护位、名称、引用与共享关系。编辑的是不带大附件的 service-login，覆盖“无关条目保存后大附件及旧历史保留”；没有覆盖附件所属条目连续编辑超过 6 MiB 历史预算后的修剪。

规模库保留预期反例：每块 21 个无问题 valid、1 个 missing_target warning、3 个 read_only（未来 schema、未知 keex 字段、旧 parent 冲突）。所以 10k 的 8800 valid 含 400 个缺失目标警告，另有 1200 read_only；不是所有条目都能直接作为正常业务记录写入。

普通关系目标必须属于本块，hub 明确集中指向第 0 块账户；缺失目标明确不在全库。独立断言还固定两订阅分别使用本块旧/新卡。动态 ID 唯一性覆盖全部当前条目，包括中央回收站。

## 当前 Mac 资源记录

以下直接取清单原始读数。oracle 每案启动三个新 Python 进程，表中时间为中位数，峰值取三次最大值；不是 p95。文件系统缓存可能已热，未清理系统缓存。

| 条目 / 附件 | 编辑后 KDBX 字节 | KDF+解密+解析中位数 | 字段投影+契约检查中位数 | 进程累计峰值 | CLI 单次保存 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1k / 小 | 374615 | 102.352 ms | 59.319 ms | 64.578 MiB | 0.207 s |
| 1k / 大 | 4565895 | 107.045 ms | 56.435 ms | 91.016 MiB | 0.332 s |
| 10k / 小 | 3639923 | 706.894 ms | 734.070 ms | 326.953 MiB | 1.342 s |
| 10k / 大 | 7830515 | 713.121 ms | 729.805 ms | 349.688 MiB | 1.442 s |

解码计时在文件字节读入后开始，不包含文件读取；领域计时包含字段提取和 Record 构造。RSS 是新进程截至该阶段的生命周期峰值，含模块、输入和解码树；macOS 原值单位为字节，Linux 路径按 KiB 转字节。CLI 每个命令也在独立 worker 中执行，单次保存含进程启动、解锁和文件写入；清单另存导入时间与各 CLI 子进程峰值。

全树源/相邻比较会同时持有多个结构，10k 两案的整体验证各约 20 秒；这与单次打开测量分开。尚未量测 Flutter、Rust/Dart 候选 writer、浏览器或 iOS 扩展。VT17 的真实设备预算没有通过。

## 验证与复核

~~~sh
python3 -B tests/fixtures/kdbx/matrix_generate.py
python3 -B -m unittest discover -s tests/vault_domain -p test_matrix.py
python3 -B -m unittest discover -s tests/vault_domain -p test_matrix_generation.py
~~~

生成分两步完成：小范围首跑 session 5e5d274c-d83a-4f63-b2ed-767e40d064c4；余下矩阵 session 7882e3d2-6353-44e3-b584-0c227b679098，exit 0，67.005 秒。当前版本无操作重跑 session c31c2aad-139c-49c6-9b56-cb720bb5ca48，七案均先核对原文件哈希再结束，不改写样本。

15 项内容测试分组首跑 79.929 秒通过，session 34ea4d23-0f86-49b7-b569-2a5024d942a7。其中所有 17 份均由 CLI export 交叉核对当前和历史字段；4.x 导出不带附件池，附件由确定性源与独立解码结果另比。7 个损坏反例覆盖私钥错配、保护降级、复合金额改值、错误的新历史、旧历史删除、附件损坏与相似未知元数据。

3 项生成守卫通过，session 22d44f5d-c32d-4f54-b893-f19d16e53af0。清单写入失败采用调用层模拟：保留已发布未登记文件、清理本进程锁、再次执行拒绝覆盖；没有实测磁盘写满、fsync 故障或崩溃原子性。强杀遗留锁需要先确认原进程状态及文件来源，不自动解锁。

review_matrix_design 做三轮有限只读审查，确认源身份映射、历史和附件差异规则、量测单位与失败范围；提出的普通关系局部性/回收站 ID 检查已补，相关测试 2.494 秒通过（session b0e37150-b7f5-4c91-9830-f3359c2e006d）。子代理没有独立执行测试，不替代人工门槛。

本轮领域测试入口合计 93 项；配合新增上游算法测试后 oracle 为 66 项，总计 159 项。最终统一回归、三套文档校验和 diff 检查由任务 fb63440068904d908064c877a8bcf6fc 的验收会话保存。

## 剩余工作与回滚

K002 首轮算法原件见 [公开来源证据](K002_ALGORITHMS.md)，后续 Argon2d 读取、派生前参数检查与 12 组有固定版本的 Rust 参考保存已补，见 [K002_LIBRARIES](K002_LIBRARIES.md)。4.x 不压缩与 278 案认证负载已补，见 [K002_RESOURCES](K002_RESOURCES.md)。未覆盖参数、官方 KeePass/KeeAgent/移动客户端、其余 4.x 参数/资源组合、秘密扫描、真机/Web 资源和人工独立审查仍待完成。Rust 参考输出尚有语义差异，K003 双候选读改写、故障/并发/恢复及生产安全门槛保持关闭。

回滚只移除这批 matrix_*、17 个新增 m*-*.kdbx、对应新测试/证据和精确忽略规则增量；上游原件单独处理。不对已有工作树 reset/restore，不改旧 46 个样本或原两份清单。没有接入真实库、安装依赖、提交或推送。

