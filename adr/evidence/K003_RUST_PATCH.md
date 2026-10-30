# K003 Rust 图标与历史保留补丁

日期：2026-10-27。输入基线为 main 的 fd44ef7；任务记录 93cc97b1ab0648d99f46d0e746d080a5。延续 [最小反例](K003_MINIMAL.md)，仅处理 L0 公开合成数据。

**隔离补丁已修复本批覆盖的图标双字段丢失、历史前插及引用索引遗漏；K003 仍为 DOING，生产写入闸门关闭。** 原候选与旧诊断保持原样，不能将补丁实验结果移记为未修补候选已经无损。安全范围仍对应 THREAT_MODEL 的 A1/A2/A3/A9/A10、T1/T7/T10。

## 1. 固定来源与改动

固定 keepass 0.15.3，沿用原 Cargo.lock 的全部依赖版本和校验和、default-features=false 与 save_kdbx4。构建器先验证缓存 crate 归档的 SHA-256，再解包到本实验临时目录；不改包缓存。派生代码保留上游 [MIT 许可证](../../tests/rust_preservation/LICENSE.keepass)，不决定 keex 的发行许可。

| 补丁 | 修改与边界 |
| --- | --- |
| [01-icons.patch](../../tests/rust_preservation/patches/01-icons.patch) | Icon 新增明确的 BuiltInAndCustom 状态，两个 getter 分别读取标准/自定义图标。贯通 Group、Entry、History 的 XML 双向转换、读取接口、引用登记和清理。删除自定义图标时保留并存的标准图标；既有 setter 仍替换整个图标，不新增测试专用生产接口 |
| [02-history.patch](../../tests/rust_preservation/patches/02-history.patch) | 编辑前快照追加到末尾，旧索引不移动；按新快照的最终索引登记图标/附件引用。XML 读取后重建当前与历史的附件反向引用。保留上游“空 tracked 编辑也产生快照”的契约 |

[build.py](../../tests/rust_preservation/build.py) 创建临时 manifest/lock，直接引用原 helper 源码；只改实验根包名和 keepass 的本地来源。每次运行格式检查、真实 Rust API 测试及 --locked --offline 构建，实验锁不得被改写。缺依赖、哈希不符、补丁或测试失败均终止，没有自动下载或替代实现。

输出为独立的 keex-preservation-writer，复用原 Cargo target；原 keex-reference-writer 保留。双图标 API 测试通过既有 candidate_minimal.make_case 生成临时合成库，再用公开 Database::parse 读取；不会修改私有字段或放开其可见性。临时源码、口令和 KDBX 随临时目录清理，未新增持久样本。

## 2. 实际验证

运行环境沿用本轮核对的 macOS arm64、Python 3.12.12、Cargo 1.98.0、Dart 3.13.5 和 KeePassXC CLI 2.8.0；旧样本生成来源仍为原登记版本。

[Python 专项](../../tests/kdbx_oracle/tests/test_rust_preservation.py) 已完成以下真实 helper 往返，所有输出均由独立 oracle 解码并由 KeePassXC 打开：

| 输入 | 往返次数 | 结果 |
| --- | ---: | --- |
| 原八类 4.1 微型案例 | 8 | 图标、空保护字段、CustomData、历史等均满足预期；混排案例只剩原根组顺序差异 |
| 无图标、仅标准、仅自定义、双字段；同时覆盖分组、当前、旧历史与新快照 | 4 | 字段存在性和值完整保留 |
| 同一条目连续编辑两次 | 2 | 两份旧历史保持原顺序，后接两份完整编辑前快照 |
| 原两类输入 × 三种 KDF × 两种外层密码 | 12 | 各案只剩根组混排差异；字段保护、历史、附件内容/保护与数量保持预期 |

比较从输入复制完整期望树，仅允许目标 UserName 和 LastModificationTime 的值变化，并显式追加旧 current 的完整快照。History 容器、未知子节点和属性都参与比较；没有扩大 oracle 的 ignore。另核对源密文字节、条目/组 UUID、解码后的数量、严格历史配对与附件内容多重集。

[Rust API 测试](../../tests/rust_preservation/tests/preservation.rs) 验证连续编辑后的引用索引、current/history 筛选、可变遍历不重复、图标替换与删除、保存重开后的相同结果。**其中 known_gap_tracked_attachment_deletion_leaves_dangling_history 是未修缺陷的正向复现，不能计入“附件生命周期无损通过”。** 当前测试数量统一维护在 [oracle 说明](../../tests/kdbx_oracle/README.md)。

复跑入口：

~~~sh
python3 -B tests/rust_preservation/build.py
python3 -B tests/run_python_tests.py --suite oracle --pattern test_rust_preservation.py -v
python3 -B tests/run_python_tests.py
cargo test --locked --offline --release --manifest-path tests/reference_writer/Cargo.toml --target-dir tests/reference_writer/target --test save_versions
~~~

最终快照的全量回归、三套文档检查、完整 index 扫描和提交结果由本批任务验收会话记录。专项通过不替代未覆盖矩阵、设备或人工审查。

## 3. 失败如何收敛

1. 独立只读复核发现初稿忽略整棵 History 会漏掉容器/嵌套内容变动；已改为构造完整期望树后比较，保留逐字段与数量检查。
2. 首次编译发现测试直接访问上游私有 icon 字段；已统一使用公开 getter，并从既有合成输入加载双图标。没有扩大库 API。
3. 实际 Rust 测试在 after reopen 阶段得到空附件反向引用，保存前同一断言通过。源码确认 xml_db/mod.rs 创建空引用集合，entry.rs 仅写名称→附件 ID，末尾只重建图标引用。02 补丁补齐附件当前/历史引用后，原失败断言通过；未降低断言或吞掉错误。

补丁、测试契约及这次修正均经独立子代理只读复核；属于同型号模型审查，不是人工独立安全验收。

## 4. 尚未解决与下一切片

- ~~**附件删除仍可破坏历史引用。**~~ 2026-10-30 由第二切片修复，见 §5。以下为当时的诊断：entry.rs 的 remove_attachment_by_name/remove_attachment_by_id 按 EntryId 清除所有历史位置；附件池可能在 tracked 快照登记前被删除。
- ~~**跨类型混排仍改变。**~~ 2026-10-30 由第三切片处理，见 §6；原诊断“不能只调换输出数组”的前提经核实不成立。
- **_merge 未启用。** 上游 src/db/merge.rs 的排序和 latest 访问仍采用“最新在前”，与本实验追加契约不同。启用前必须统一合并顺序、最新项选择及引用重建；当前补丁不声称适用于全部 feature。
- 原有不存在的 CustomIconUUID 过滤行为未改变；历史裁剪/清空（已由 §8 处理）及其它资源删除路径尚未完整验证。未知 XML、未引用附件池、旧格式原样写回、资源预算、取消/崩溃/并发保存、Web/iOS/真机和多来源样本仍未达到生产门槛。

K009 继续负责发行许可证与旧库只读/显式升级策略。K001/K002/K068 的 REVIEW 与 K069 的 DOING 不变。回退只需撤销本实验目录、对应测试及说明增量；原 helper、锁文件、固定 KDBX、manifest、oracle 与真实用户资料均未改变。

## 5. 第二切片：附件生命周期（2026-10-30）

基线为 main 的 31e9d4b。新增 [03-attachments.patch](../../tests/rust_preservation/patches/03-attachments.patch)，只改 entry.rs；01/02 不变。**删除或同名替换附件不再破坏历史引用；K003 仍为 DOING，生产写入闸门关闭。**

| 根因 | 改法 |
| --- | --- |
| remove_attachment_by_name/by_id 用 `entry_id != id` 过滤，一次清掉该条目所有版本（含历史）的引用；引用集合一空就删附件内容 | 只去掉当前这个版本的 `(条目, 历史索引)` 引用；同一版本另有名称仍指向该附件时不去掉；最后一个引用消失才删内容（与上游语义一致） |
| tracked 编辑在闭包结束（Drop）时才把编辑前快照放进历史并登记引用；闭包里删附件时快照还没登记，内容先被删掉 | track_changes 开始时就把快照追加到历史末尾并登记附件/图标引用，删除 Drop 中的同一逻辑。编辑结束后的历史与原契约相同：空 tracked 编辑仍产生一份快照 |

新增 4 项 Rust API 测试，替换原 known_gap 测试：

| 测试 | 覆盖 |
| --- | --- |
| tracked_attachment_deletion_keeps_content_for_history | tracked 删除后两份历史仍能读到原字节和保护位，当前版本没有该附件；保存重开后相同 |
| same_name_replacement_keeps_previous_content_in_history | 同名替换后当前是新内容、历史是旧内容，两者是不同附件；重开相同 |
| shared_and_history_only_attachments_survive_tracked_removal | 用已登记的 v41-vault-edit1（KeePassXC 写出）：shared.txt 同时被 Login 当前、Login 历史和另一条目引用，blob.bin 只在历史里；删除后内容和每处引用都在，重开后再从另一条目直接删除，Login 历史仍能读到 |
| releasing_the_last_reference_still_deletes_content | 正控制：没有任何版本引用时照常删除内容；删除整个条目后其附件随之删除 |

**先红后绿，均为实际运行：** 只应用 01/02 时，4 项新测试全部失败：删除后内容不在；同名替换后读取历史版本直接 **panic**（attachment.rs:120，“AttachmentRef points to non-existent attachment”），即上游原状下读这份历史就会崩溃；共享样本中 Login 旧历史 h0 对 shared.txt 的引用被误清。加上 03 后 7 项 Rust 测试全部通过；Python 专项 4 项（含原 8 类微型往返和 12 组算法矩阵，KeePassXC 重开）通过，结果与第一切片相同，只剩已知混排差异。

过程中自己的两处测试错误：期望数组未按字节序排序；误以为样本 Login 只有 1 份历史（实际 2 份，第 2 份不带附件），把新快照写成索引 1。两处都改测试本身，并在修正后重新确认缺 03 时确实失败，没有改补丁去迁就测试。

样本输入不另存：build.py 按 vault_manifest 登记的哈希核对 v41-vault-edit1 后写进临时目录，随临时目录清理。上游 entry.rs 本身在默认 rustfmt 配置下就有 17 处格式差异，补丁前后数量不变；构建的格式检查只覆盖 helper 与测试代码。

仍未解决：

- **跨类型混排**当时仍是下一切片，已由 §6 处理。
- 闭包执行期间，快照已经出现在历史里（原实现要等闭包结束）。编辑结束后的结果相同，但闭包里读历史长度的调用方会看到多一份；本仓库没有这样的调用。
- 对历史版本调用 add_attachment 时，上游仍按“当前版本”登记引用；只能经 foreach_entry_mut 回调拿到历史版本，本切片没改，也没测。
- “同一版本两个名称指向同一附件”的分支已实现，但现有样本里没有这种结构，没有测试覆盖。
- _merge 仍未验证，历史裁剪/清空已由 §8 处理；以上测试只证明这几条生命周期路径，不是附件整体无损通过。

## 6. 第三切片：组与条目的写出顺序（2026-10-30）

新增 [04-child-order.patch](../../tests/rust_preservation/patches/04-child-order.patch)，只改 format/xml_db/group.rs 的 db_to_xml：**同一分组下先写条目、后写子组**。之前是先子组后条目。

**为什么这样改，而不是保留任意交错顺序：** 先查了参考客户端怎么做。

| 来源 | 结论 |
| --- | --- |
| keepass 0.15.3 本身 | 数据库模型里每个分组的子组、条目是两个独立的 IndexSet；XML 解析时按出现顺序分别放进去，所以同类型内部顺序保留，跨类型交错在模型里就丢了，写出时再统一先组后条目 |
| KeePassXC 2.7.12 源码 | [KdbxXmlWriter.cpp](https://github.com/keepassxreboot/keepassxc/blob/2.7.12/src/format/KdbxXmlWriter.cpp) 第 341–347 行先写条目、再写子组；KdbxXmlReader.cpp 第 489–590 行把子组和条目收进两个列表；Group.h 用 m_children、m_entries 两个列表 |
| KeePass 2.x | PwGroup 的 m_lGroups、m_lEntries 两个列表，PreOrderTraverseTree 先遍历条目再遍历子组（读的是非官方镜像 dlech/KeePass2.x，未对官方发行包逐字核对） |
| 实际文件 | KeePassXC 写出的 v31/v41-vault、m41-passkey 和 kdbxweb 原件 Argon2id.kdbx，凡同时含组和条目的分组都是“条目在前”；未修的 keepass-rs、kdbx.dart 输出都是“子组在前” |

所以 KeePass 生态里没有哪个实现能表示任意交错；§4 和实施路线原先要求“保留跨类型序列、不能只调换输出数组”，前提不成立。合适的目标是与参考客户端一致的写出顺序：它们写出的文件顺序原样保留，它们自己也表示不了的交错同样被规范成“先条目、后子组”。这不改变比较器规则。

内层保护流按文档顺序加密：这里调用顺序和输出顺序一起改，两者仍一致，所有受保护值都由独立 oracle 解密核对。

**先红后绿，均为实际运行：** 先改 Python 专项的期望（未改补丁）：12 组矩阵从“只放行根组顺序差异”改为“全文无差异”；构造的交错微型案例从笼统放行“顺序变了”改为精确断言“条目在前、子组在后、各自相对顺序不变”。只用 01–03 时这两项失败（微型案例输出是子组在前，12 组每组都报根组顺序差异）；加上 04 后 Python 专项 4 项与 7 项 Rust API 测试全部通过，**原 12 组算法矩阵按完整期望树比较不再有任何差异**，KeePassXC 均能重开。

另用 04 版 helper 对 K002 黄金样本 g41-rich、g41-big 各做一次往返探针：差异只剩目标条目的 UserName、修改时间和新增历史。注意这两份同样由 KeePassXC 写出，它已先丢掉部分元数据，所以不能据此说明未知内容被保留。

仍未解决：

- 嵌套分组里的同类顺序与本切片同一段代码，但现有 4.1 输入里同时含组和条目的只有根组；helper 只接受 4.1，所以 kdbxweb 原件里嵌套的混合分组没有进这组往返。
- ~~未经参考客户端改写的未知 XML、未引用附件池~~ 已由 §7 验证和处理。
- _merge、旧格式原样写回、资源预算、取消/崩溃/并发保存、Web/iOS/真机与多来源样本仍未达到生产门槛（历史裁剪/清空已由 §8 处理）；K003 仍为 DOING，生产写入闸门关闭。

## 7. 第四切片：未知内容（2026-10-30）

新增 [05-unknown-content.patch](../../tests/rust_preservation/patches/05-unknown-content.patch)。**未知内容现在不会被静默丢掉，也不会把密码解错；代价是这类文件不能保存。** K003 仍为 DOING，生产写入闸门关闭。

### 发现了什么

输入直接构造 XML，没有经过 KeePassXC 改写（它会先删掉这些内容）。只用补丁 01–04 时：

| 输入 | 结果 |
| --- | --- |
| 条目、Meta、Root、文件根、历史版本、Times 里的未知元素；条目、字段、分组上的未知属性 | **静默丢失**：能打开、能保存，内容没了 |
| 未知元素里带受保护值，放在其它受保护值之前 | **静默破坏密码**：40 次尝试（未知值长度 1–40）全部保存成功且全部解错，例如 `a` 变成 `p`、`K` 或 U+FFFD |
| 分组里的未知子元素；String 之间的未知元素 | 打不开（模型结构不接受），安全但读不了 |
| 没有条目引用的附件池项 | 保留 |

第二行最严重。受保护值共用一条内层流，按文档顺序消费；解析器跳过未知元素时没消费它那段密钥流，后面每个受保护值都用错位的密钥流解密，无效 UTF-8 还被有损替换，所以没有任何报错，保存时错误明文被重新加密写回。同样的错位也会出现在文档顺序与解密顺序不一致时：解密固定先 String 后 History、先 Meta 后 Root。现有 61 份登记样本都没有这种结构，没有证据说明真实文件里常见；但一旦碰到就是不可恢复的数据破坏，所以必须拦。

### 为什么是拦截而不是保留

ADR-0001 §3 的要求是“遇到不可保证保留的数据禁止写入”。要真正保留任意未知 XML，得给 serde 模型的每一层加捕获并按原位置写回，还要处理其中受保护值的重新加密，改动范围不是小补丁，这里没有做。

新增的 known.rs 在解析前扫描一次解密后的 XML（此时受保护值还是密文），对照“模型实际有字段”的元素和属性表：

| 情况 | 行为 |
| --- | --- |
| 未知元素、属性、容器元素里的游离文字；历史版本里嵌套的 History（模型会丢弃） | 能打开和读取；`Database::save` 返回 `UnknownContent`；路径由 `unknown_content()` 给出，只含元素名，不含值，最多 32 条 |
| 未知内容带 `Protected="True"`，或属性加在模型不解密的已知元素上；String 出现在 History 之后；Meta 出现在 Root 之后 | 拒绝打开（`UntrustedProtectedValues`） |
| 模型结构不接受的两种形状 | 维持原来的打不开 |

拦截放在库里，helper 不用改，现有调用自动生效，也没有绕过开关。

### 验证（均为实际运行）

- **先红后绿：** 只用 01–04 时 17 个子用例失败（8 个拒绝打开、9 个拒绝保存）；加上 05 后 Python 专项 9 项、Rust API 10 项全部通过。
- **不误拦：** Rust 测试打开全部 61 份登记样本（KeePassXC 2.7.12 的 3.1/4.0/4.1、kdbxweb 原件、两个候选的输出），`unknown_content()` 都为空。另用本机 KeePassXC 2.8.0 现场写一份富样本，往返后编辑条目以外没有差异。
- **表不比模型宽：** 用例给表里每个元素放非默认值后往返，独立 oracle 全文比较无差异。翻转 MemoryProtection 的变体只核对全文和“KeePassXC 能打开”，因为 KeePassXC 导出时会按这组开关重新标记标准字段。
- **对照 KeePass 2.x 写入器：** 读 KdbxFile.Write.cs（非官方镜像 dlech/KeePass2.x，未对官方发行包逐字核对），它写的 81 个元素名里只有 `MasterKeyChangeForceOnce` 不在表中，且只在该设置为真时才写。模型确实会丢它，所以这类文件被拒绝保存是对的。但手头没有官方 KeePass 实际写出的文件，这一点只来自读源码。
- **开销：** 打开 10000 条目、约 7.6 MB 的样本，未打补丁的 helper 0.35 秒、127 MB，全部补丁后 0.43 秒、130 MB。只测一次，且两个二进制还差其它补丁，只能看量级。

**kdbx.dart 对照（未修补）：** 未知元素和属性都保留，分组里的未知子元素也保留；未知受保护值这一例报错、没有产出文件。这一项它比 keepass-rs 好，K009 要算进去。

### 仍未解决

- 带未知内容的文件只能读不能存，这是有意的取舍；如果真实使用中常见，要回头评估保留方案。
- 表来自 keepass 0.15.3 的模型字段，升级候选版本必须重新核对。
- XML 注释和处理指令不算未知内容，保存时会丢；它们不参与 oracle 比较，没有验证。
- 这个静默破坏是上游缺陷，本轮**没有向上游报告**（公开发布需要项目负责人决定）。
- _merge、旧格式写回、取消/崩溃/并发保存、Web/iOS/真机和多来源样本仍未达到生产门槛（历史裁剪已由 §8 处理）。

## 8. 第五切片：历史裁剪（2026-10-30）

新增 [06-history-limits.patch](../../tests/rust_preservation/patches/06-history-limits.patch)。**tracked 编辑现在按库里的上限裁剪这一个条目的历史，结果和 KeePassXC 2.8.0 对照一致；被删版本独占的附件内容不再留在文件里。** K003 仍为 DOING，生产写入闸门关闭。

### 发现了什么

上游完全不裁剪：`HistoryMaxItems`、`HistoryMaxSize` 只读写，不生效。上限设成 3 的库，编辑多少次历史就涨多少份。参考客户端下次编辑这个条目时才会替它删。

上游的公开字段 `history` 是唯一能删历史的路径，实测有两个问题：`entry.history = None` 之后，只被历史用的附件内容还在，保存重开仍是 3 份（用户以为删了，内容还在文件里）；遍历这些附件的引用直接 panic（entry.rs，`Option::unwrap()` on `None`）。

### 规则从哪来

先读了两个参考客户端的实现（[KeePassXC 2.7.12 Entry.cpp](https://github.com/keepassxreboot/keepassxc/blob/2.7.12/src/core/Entry.cpp) 的 `truncateHistory`、`size`；KeePass 的 PwEntry.cs，读的是非官方镜像 dlech/KeePass2.x，未对官方发行包逐字核对）。

| 决定 | KeePassXC | KeePass | keex 补丁 | 为什么 |
| --- | --- | --- | --- | --- |
| 何时裁剪 | 编辑结束时，只裁这个条目 | 同左 | 同左；打开、保存都不裁 | 没人编辑的条目不该因为打开一次就少历史 |
| 留哪些 | 最新的连续若干份，合计不超过上限 | 同左 | 同左 | 两个客户端在这点上一致 |
| “最旧”怎么判断 | 列表位置 | 修改时间 | **修改时间**，相同时靠后的算新 | 见下面的反例 |
| 大小怎么算 | 字段、关联窗口、附件、自定义数据、标签的字节数 | 估算进程内存（每条目固定 276 字节，字符按 2 字节） | **KeePassXC 的算法** | 按字节、结果确定，能和本机 CLI 对照；KeePass 算出来更大，所以裁得更早，两边没有共同的数 |
| 没写上限 | 按默认 10 份、6 MiB | 同左 | **不裁剪** | 文件没说要删，不替用户决定删数据 |
| 负数 | -1 不限，其它负数忽略（仍用默认） | 负数都不限 | 负数都不限 | 同上 |
| 自定义图标 | 不随版本删除 | 不随版本删除 | 同左 | 图标属于整个库，可以再用 |

**按时间而不是按位置，是实测过的。** 上游 keepass-rs 写出的文件历史是最新在前。对这样的文件（v4、v3、v2、v1、v0，上限 3），KeePassXC 留下 v1、v0、v5，把更新的 v4、v3、v2 删了；补丁留下 v4、v3、v5。正常顺序的文件两种判断结果相同。

**唯一和 KeePassXC 对不上的地方：** 它读入自定义数据时会在内存里多一项 `_LAST_MODIFIED`，也计入大小，它的源码注释自己承认这让长度不可预测。实测这一项 14 + 28 = 42 字节：合成样本在我们算的 479 字节处放得下的版本，KeePassXC 要到 521 才放得下。这项会被它写进文件，所以它写过的文件我们会按文件内容算进去；只有文件里还没有这一项时才差这几十个字节，后果是边界上多留一份，不影响数据正确性。

### 改法

一处裁剪，全部走同一条路：`track_changes` 追加快照后调 `trim_history`；`EntryMut::trim_history()` 给“调低上限之后”用；`clear_history()` 给“用户清空历史”用；三者最后都经过 `retain_history`。它重排历史，把附件和图标里的引用改到新位置（引用记的是历史下标，删掉前面的版本后面的都要动），只删除这次失去最后一个引用的附件。文件里本来就没人引用的附件不是这次造成的，留着。

### 验证（均为实际运行）

- **先红后绿：** 不打 06 时，新的 Python 对照 22 个子用例失败：21 个是历史一份不删，1 个是当时还没查清的 KeePassXC 大小差异（上面那项，之后把自定义数据拆成单独用例）；打上后 Python 11 项、Rust API 15 项通过。全量回归 oracle 180 项 + 领域 93 项，没有跳过；原 12 组矩阵和全部登记样本不受影响。
- **和 KeePassXC 对照：** 同一份合成输入，补丁库和 `keepassxc-cli edit` 各改一次，独立 oracle 读两边结果。份数上限 -1、0、1、3、5、6 全部一致；大小上限对每一份版本都测“刚好放得下”和“差一个字节”，一致。样本带中文、标签、关联窗口、附件，字节数和字符数不同，算错会露出来。
- **全文比较：** 补丁库的输出和“只改用户名、修改时间、裁掉指定版本”的期望树比较，没有其它差异。
- **附件：** 只被删掉版本用的内容离开文件，还被保留版本或其它条目用的内容留下，和 KeePassXC 一致。
- **故意改坏：** 分别去掉“重新编号”“释放附件内容”“tracked 编辑时裁剪”，Rust 测试都能抓到（1、3、1 项失败）。

### 仍未解决

- **公开字段 `entry.history` 还能直接赋值，危险没有消除。** 把它改成私有要动 helper 和未修补候选共用的代码，这里只加了注释和正确入口；真正接入产品时要在核心层封住。`History::add_entry` 同理。
- **时钟回拨：** 如果刚生成的快照时间比其它历史都早（比如设备时钟慢），它会先被删，KeePass 也一样。没有处理。
- **标准字段缺失：** KeePassXC 总把 5 个标准字段名计入大小，缺字段的文件这里少算几个字节，只影响边界上多留一份。
- 调低上限后要不要裁全库由产品决定，这里只给单条目入口；官方 KeePass 没实际跑，它的规则只来自读源码。
- 对照用的是本机 KeePassXC 2.8.0，读的源码是 2.7.12；两版结果一致只说明这些用例没变。
- _merge、旧格式写回、取消/崩溃/并发保存、Web/iOS/真机和多来源样本仍未达到生产门槛。

## 9. 第六切片：和 KeePassXC 轮流编辑（2026-10-30）

这是 K003 验收里的“第三方可重开并再编辑”。之前只对**未修补**的候选做过（K003.md），补丁库没做过。**现在补丁库和 KeePassXC 轮流改同一份文件，补丁库这边每一步除目标条目外没有任何差异。** 过程中查出两个真实缺陷，由 [07-absent-defaults.patch](../../tests/rust_preservation/patches/07-absent-defaults.patch) 修复。K003 仍为 DOING，生产写入闸门关闭。

### 测了什么

| 用例 | 过程 | 比较 |
| --- | --- | --- |
| 11 份输入（KeePassXC 写的 vault、passkey，黄金样本 g41-rich，8 个合成微型案例） | 补丁库 → KeePassXC → 补丁库 → KeePassXC 导出核对 → KeePassXC → 补丁库，共 5 次编辑 | 补丁库每一步全文比较，只许有这次编辑；最后核对历史链 round-1 到 round-4 |
| 结构变动 | KeePassXC 建组、新建条目、移动条目、删除到回收站再彻底删除、改网址和备注、删附件、导入附件；然后补丁库读回再存，KeePassXC 再改 | 全文比较保证以上改动一处不丢；再逐项断言新路径、DeletedObjects、附件 |
| 只留必需元素的文件 | 所有可选元素都去掉，补丁库改一次 | 多出来的元素必须在已知等价清单内；KeePassXC 分别导出输入和输出再比较，除这次编辑外相同 |

### 查出的两个缺陷

之前的合成样本每个条目都显式写了这些元素，所以一直没暴露。

| 缺陷 | 表现 | 修法 |
| --- | --- | --- |
| 凭空写 `QualityCheck` | 上游无条件写 `<QualityCheck>True</QualityCheck>`。KeePass 和 KeePassXC 只在值为 false 时才写，所以它们新建的条目经补丁库存一次就多一个元素（历史版本也一样） | 模型改成 `Option<bool>`：文件写了什么就是什么，没写就还是没写。这改了公开字段的类型 |
| `IsExpanded` 读反默认值 | 文件没写时读成 false 再写回，分组从展开变成折叠。KeePass（PwGroup.cs 第 68 行）和 KeePassXC（Group.cpp 第 45 行）默认都是展开 | 没写时按展开读。这是真实的语义变化，但真实客户端都会写这个元素，只影响其它实现写的文件 |

### 还会多出来、但确认等价的元素

文件没写时，保存后仍会多出 `<Times/>`、空的 `<CustomIcons/>`、`<CustomData/>`、`<DeletedObjects/>`，以及分组的 `IsExpanded=True`、`EnableAutoType=null`、`EnableSearching=null`。这份清单写死在测试里，出现新元素就会失败。KeePassXC 分别导出两份文件比较，结果相同，这是它们等价的依据；KeePass 没实际跑。

### KeePassXC 自己的变动（单列，不算候选的问题）

本机 2.8.0 编辑一个条目时还会动：各处 `_LAST_MODIFIED`，Meta 里的 `KPXC_RANDOM_SLUG`，目标条目的 LastAccessTime。只在合成输入上出现：带自定义图标的节点 IconID 被归零（这正是补丁 01 要保留的双字段，它自己不保留）；条目自定义数据被去掉单项时间并补上 `_LAST_MODIFIED`。测试只放行这些，其它变动直接失败。

### 验证（均为实际运行）

- **先红后绿：** 不打 07 时，“只留必需元素”和“结构变动”两项失败（后者正是 KeePassXC 新建条目多出 QualityCheck）；打上后本切片 3 项通过。全量回归 oracle 183 项 + 领域 93 项，没有跳过；Rust API 15 项。
- **开销（Apple M1 Pro，macOS 26.6.2，每项 5 次取中位数）：** 未修补和 01–07 全部补丁基本没有差别。

| 输入 / 算法 | 未修补 | 全部补丁 |
| --- | --- | --- |
| v41-vault-edit1（39 KB），AES-KDF | 0.06 秒，9.9 MB | 0.06 秒，9.9 MB |
| v41-vault-edit1，Argon2d | 0.04 秒，17.7 MB | 0.04 秒，17.7 MB |
| m41-scale-1000-large-edit1（4.6 MB），AES-KDF | 0.23 秒，56.6 MB | 0.27 秒，56.8 MB（一次异常 0.59 秒，其余 0.24 附近） |
| m41-scale-1000-large-edit1，Argon2d | 0.22 秒，60.5 MB | 0.22 秒，61.3 MB |

### 补丁累计规模（给 K009 算修补成本）

7 个补丁，改动 10 个文件，新增 554 行、删除 101 行；其中 known.rs 的元素表约 250 行。**对上游公开 API 有两处不兼容：** `Icon` 枚举（01）和 `quality_check` 的类型（07），另外 `Database::save` 多一种错误。升级候选版本时每个补丁都要重新核对，known.rs 的元素表尤其要逐项比对。

### 仍未解决

- 只和 KeePassXC 2.8.0 轮流过。官方 KeePass、手机客户端（KeePassDX、Strongbox 等）都没跑，它们写的文件可能带本切片没见过的元素；未知元素会被拒绝保存而不是丢失，但那意味着这些用户的库只能读。
- 这些往返都只有 KDBX 4.1：补丁库不能写旧版本，3.1/4.0 的策略还等 K009。
- _merge 未启用。ADR-0001 的同步方案是自己做三方比较，大概率用不上上游这部分，到 K009 时明确。
- 取消/崩溃/并发保存不在这个库的层面，属于产品的安全核心；Web/iOS/真机没有验证。

