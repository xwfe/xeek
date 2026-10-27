# K003 最小反例与修补范围

日期：2026-10-27。对应 [K003](K003.md) 的合成预实验增量。输入基线为 main 的 4d1d368；任务记录 72e726a81c0d4ecfa5955716fb93212c。

**本批交付的是可复现的缺陷诊断与修补边界，没有修复候选库，也没有开放生产写入。** 主任务状态仍以 [TASKS](../TASKS.md) 为准，K002/K069 与人工独立门槛没有被本批替代。涉及 THREAT_MODEL 的 A1/A2/A3/A9/A10 和 T1/T7/T10：只用公开合成密钥与资料，防止错误保存、输入构造和测试输出掩盖数据丢失。

后续隔离 Rust 补丁及实际修复结果见 [K003_RUST_PATCH](K003_RUST_PATCH.md)；以下保留本批原始诊断和当时的修补估计。

## 1. 新证据修正了什么

固定候选：keepass-rs 0.15.3、kdbx.dart 2.5.0。运行环境实际核对为 Python 3.12.12、Cargo 1.98.0、Dart 3.13.5、macOS arm64、KeePassXC CLI **2.8.0**。旧登记样本的生成客户端仍是 KeePassXC 2.7.12；本次重开使用 2.8.0，不能把这两个版本混成一个来源。

| 反例 | 实际结果 | 对旧报告的修正 |
| --- | --- | --- |
| 空标准字段 + 空自定义受保护字段 + 后续非空受保护字段；当前条目和历史均包含 | Dart 在 3.1/Salsa20、4.0/4.1/ChaCha20 内层流下，丢两个空值的保护标记；后续非空值和保护位仍正确。Rust 4.1 保留 | 缺陷不只影响空标准字段；也影响空自定义字段和历史 |
| Meta、Group、Entry、History 的 CustomData Item 均含时间 | Dart 丢 Meta、Entry、旧历史和新增历史的 LastModificationTime，Key/Value 保留；Group 的时间保留。Rust 保留各处 | 不能再将缺陷范围写成只有 Meta；Group 是有用的保留对照 |
| 只有显式标准 IconID，未设置 CustomIconUUID | 两个候选都保留 Group 的 48 和 Entry 的 0 | 推翻“Rust 无条件删除默认 IconID”的泛化 |
| 同时设置标准 IconID 与 CustomIconUUID | Rust 保留自定义图标引用，删除标准 IconID；Dart 保留两者。另以非默认 IconID=1 验证相同触发机制 | 根因是双字段不能进入同一个模型，不是默认值规范化 |
| 自定义图标带 UUID、Data、Name、LastModificationTime | Dart 保留 UUID/像素，丢 Name/时间；Rust 保留这四项 | 4.1 图标元数据缺口仍成立 |
| 根组子节点按 Entry A / Group 1 / Entry B / Group 2 混排 | 两个候选输出 Group 1 / Group 2 / Entry A / Entry B；两组和两条目各自的相对顺序保持 | 跨类型顺序与同类型顺序分开描述，不扩大 ignore |
| 两条旧历史后编辑当前条目 | Rust 输出新增快照在前，Dart 在后；本例旧快照内容保持 | 历史方向不同，不是旧历史整体丢失 |
| 直接对上游 API 保存 3.1、4.0、4.1，绕过本地 helper | Rust 对 3.1/4.0 返回 UnsupportedVersion，输出缓冲区为空，原对象版本未变；4.1 能保存并重开 | 是上游能力限制；它拒绝旧格式保存，并非自动静默升级 |
| 已登记 Argon2id 4.0/4.1、3.1 外层 ChaCha20 原件 | oracle 能读；Dart 实际 helper 报 database_open_failed，未创建输出 | 继续确认候选能力缺口，不把输入损坏当成不支持 |

最后一行复用已有三份小原件，不声称又生成了新客户端来源。其它微型输入共 12 个，密文 1534–1911 字节，最多两个当前条目、两个子组、两份旧历史，无附件。输入不是由 KeePassXC 重写后再交给候选，避免它先剥掉目标元数据。

## 2. 实现与证据链

- [candidate_minimal.py](../../tests/fixtures/kdbx/candidate_minimal.py)：复用已有 source、mutate、v4_payload 和已登记公开源，构造确定性的微型 XML/密文。转换明文导入用的 ProtectInMemory、4.x 二进制时间和 3.1 HeaderHash；内层流按最终文档顺序消费。没有新增密码算法或生产保存入口。
- [test_candidate_minimal.py](../../tests/kdbx_oracle/tests/test_candidate_minimal.py)：按锁文件离线重建真实 Rust/Dart helper；输入先由 oracle 解码，再让 KeePassXC 打开并核对当前字段。候选输出由 oracle 直接检查目标字段、保护位、图标、时间、顺序和历史，不借参考客户端的标准化结果判丢失。
- [save_versions.rs](../../tests/reference_writer/tests/save_versions.rs)：直接调用 keepass 的 open/save；两个旧格式的拒绝检查与 4.1 正控制相互对照。只读已有文件，输出仅存在内存；来源哈希由既有 Python 全量回归检查，本 Rust 测试不重复造一套哈希实现。

微型往返同时核对源密文字节未变、当前条目/分组 UUID、无附件和每条历史的实际数量。helper 返回的是序列化前内存计数，因此额外用 oracle 解码后的数量交叉核对；历史配对使用严格长度检查，不能因 zip 截短而漏掉丢失的尾部。

新密文均进入 TemporaryDirectory，结束自动清理；没有新增持久 KDBX、修改旧样本/manifest、修改候选 helper 或放宽 oracle 规则。新增源码经工作树秘密扫描无需新增例外。构建沿用已有锁文件与缓存，没有新增依赖或安装工具链。

## 3. 源码根因与补丁成本

以下位置均为实际锁定包内的相对路径；Rust 来自 keepass 0.15.3 固定缓存，Dart 来自项目内 kdbx-2.5.0。S/M/L 是修补范围估计，不是工期承诺；尚未实施任何候选补丁。

| 问题 | 已定位的边界 | 最小修补范围与验证 | 规模 |
| --- | --- | --- | --- |
| Rust 标准/自定义图标共存 | src/db/types/icon.rs 的 Icon 是 BuiltIn / Custom 互斥枚举；XML 层本来有两个独立字段 | 先让模型和 XML 双向转换保留两项，不能在保存末尾猜默认值。覆盖 Group、Entry、History，缺省/默认/非默认以及不存在的自定义图标引用 | M |
| Rust 历史前插 | src/db/types/history.rs 的 add_entry 使用 entries.insert(0, entry) | 插入和读写顺序一起审查，核对依赖“最新在前”的调用方及历史裁剪；至少覆盖两份旧历史、连续编辑和裁剪边界 | S–M |
| 两候选混排顺序 | Rust 实际输出先组后条目，具体损失阶段尚待定位；Dart kdbx_group.dart 分开收集，保存时先 groups 后 entries | Rust 先定位解析、模型转换和写出中的损失位置，再评估如何保存跨类型序列并贯通增删/移动；不能仅调换两个数组。若拟调整项目语义契约，先明确审查，不能直接扩大比较器忽略项 | M（待源码定位） |
| Rust 旧格式写入 | src/db/save.rs:17 拒绝 KDB3；src/format/kdbx4/dump.rs:31 只接受 KDB4(1) | 原格式写回是独立能力工程，不能当本批小补丁。可评估“旧格式只读 + 用户明确确认后升级”，按 ADR-0001 另验备份、告知和恢复 | L / 产品策略 |
| Dart 空保护值 | protected_salt_generator.dart 两种 decryptBase64 对空 bytes 返回 null；kdbx_format.dart 跳过 ProtectedValue 注册 | 空密文应形成空受保护值且不消费流；覆盖两种内层流、标准/自定义字段、前后非空值和历史，不做字段名特判 | S |
| Dart 图标与 CustomData 时间 | kdbx_meta.dart 的图标模型只存 UUID/Data；kdbx_custom_data.dart 用 Map<String,String> 并清空重建 Item | 扩充模型、读写、复制及合并语义，保留 Item 元数据和未知扩展。Group 当前保留路径不能被修补破坏 | M |
| Dart Argon2id | crypto/key_encrypter_kdf.dart 只登记 AES/Argon2d UUID，Argon2 类型固定为 0 | 复用现有后端做类型/参数分派；独立向量、参数边界、盐轮换、错误密钥及附加参数的显式支持/拒绝都要重验 | M |
| Dart 3.1 外层 ChaCha20 | kdbx_format.dart 的 3.x 读写固定 AES；kdbx_header.dart 的 3.x 盐生成还固定 16 字节 IV | 读、写和 nonce 长度一并分派，ChaCha20 不应用 AES 填充；保留 StreamStartBytes、分块哈希及 HeaderHash 验证 | M |

**推荐的下一切片：优先做隔离的 Rust 保留补丁实验。** 先处理图标双字段与历史顺序，再处理混排顺序；每个补丁分别复跑本批反例和原大样本矩阵。原因是当前 Rust 算法覆盖更完整，Dart 还需补 Argon2id、3.1 ChaCha20、模型元数据，并另过运行资源验证。该建议不是 K009 最终选型。

优先把可独立说明的小补丁准备成上游可审查的内容；本地实验可以保存明确版本的补丁，不直接修改包缓存。没有向上游发送 Issue/PR，也没有获准公开发布。若模型改动超出可维护的小补丁边界，再进入换库研究，不预先维持两个生产 writer。

发行许可证仍由 K009 决定：固定 Rust 包为 MIT，Dart 包为 GPL-3.0。候选的独立测试进程与产品实际分发/链接方式分别评估，本批没有决定 keex 的发行许可证，也没有把 Dart 代码移入产品。

## 4. 复跑、失败与复核

仓库根目录执行：

~~~sh
python3 -B tests/run_python_tests.py --suite oracle --pattern test_candidate_minimal.py -v
cargo test --locked --offline --release --manifest-path tests/reference_writer/Cargo.toml --target-dir tests/reference_writer/target --test save_versions
python3 -B tests/run_python_tests.py
cargo fmt --manifest-path tests/reference_writer/Cargo.toml -- --check
python3 -B tests/dart_candidate/generate.py
python3 -B tests/reference_writer/generate.py
python3 -B tests/secret_scan/scan.py --worktree
~~~

测试数量只维护在 [oracle 说明](../../tests/kdbx_oracle/README.md)。最小反例每次真实构建，不允许缺工具时静默跳过；领域单独入口不依赖这两个 helper。所有通过只表明诊断与正控制成立，不能当作候选已经修好。

本批实际经历的失败：

1. 首次 Dart 离线构建报缓存不存在：进程继承的 PUB_HOSTED_URL 指向镜像，项目缓存与锁文件却来自 pub.dev。诊断后仅给构建子进程指定锁文件源，仍使用 --offline --enforce-lockfile；没有下载、升级或改全局配置。
2. 首轮图标断言失败：两个默认 IconID 实际保留，说明反例缺少 CustomIconUUID。将纯标准图标变成正控制，增加双字段反例后通过，并补非默认值断言；没有修改比较器掩盖失败。
3. 独立只读审查发现历史配对可能因 zip 截短假通过。已补最终密文解码计数、逐条数量、严格配对及两组混排，修正后再次复核无新增阻断项。Rust 直接版本探针也经过独立只读复核。

分项诊断与 Rust 版本探针已实际运行。最终源码快照的全量回归、文档检查、完整 index 扫描及提交结果由本批任务验收会话记录；不把预修改的执行记录冒充最终快照。审查由同型号独立子代理进行，不是人工独立安全验收。

Rust 的 Group/Entry 双向转换位置、混排顺序丢失阶段及历史裁剪依赖尚未完成源码定位；相关规模估计保留条件，不能据此承诺单点修补。

## 5. 未解决与回退

尚未完成：候选库修复、官方 KeePass/KeeAgent/手机客户端来源、候选的 1k/10k/大附件资源测试、取消/崩溃/并发保存、浏览器及 iOS 扩展、人工独立复核。未知 XML/未引用附件等未覆盖边界也不能凭这组微型测试宣称无损。所有生产门槛保持关闭。

回退只撤销本批新增的三个测试源码文件及对应说明/交接增量；不会触碰原黄金样本、两份 writer manifest、候选 helper、锁文件或任何真实密码库。临时密码库没有作为交付物留存。
