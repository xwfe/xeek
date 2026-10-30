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
- **跨类型混排仍改变。** XML Group 的 children 本来保留 Group/Entry 顺序；后续进入数据库模型并写出时失序。下一步检查分开的组/条目集合、增删移动及重组路径，不能误称 XML 解析器先拆成两个数组，也不能只调换输出数组。
- **_merge 未启用。** 上游 src/db/merge.rs 的排序和 latest 访问仍采用“最新在前”，与本实验追加契约不同。启用前必须统一合并顺序、最新项选择及引用重建；当前补丁不声称适用于全部 feature。
- 原有不存在的 CustomIconUUID 过滤行为未改变；历史裁剪/清空及其它资源删除路径尚未完整验证。未知 XML、未引用附件池、旧格式原样写回、资源预算、取消/崩溃/并发保存、Web/iOS/真机和多来源样本仍未达到生产门槛。

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

- **跨类型混排**仍是下一切片（见 §4）。
- 闭包执行期间，快照已经出现在历史里（原实现要等闭包结束）。编辑结束后的结果相同，但闭包里读历史长度的调用方会看到多一份；本仓库没有这样的调用。
- 对历史版本调用 add_attachment 时，上游仍按“当前版本”登记引用；只能经 foreach_entry_mut 回调拿到历史版本，本切片没改，也没测。
- “同一版本两个名称指向同一附件”的分支已实现，但现有样本里没有这种结构，没有测试覆盖。
- _merge、历史裁剪/清空仍未验证；以上测试只证明这几条生命周期路径，不是附件整体无损通过。
