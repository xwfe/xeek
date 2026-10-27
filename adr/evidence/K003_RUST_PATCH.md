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

- **附件删除仍可破坏历史引用。** entry.rs 的 remove_attachment_by_name/remove_attachment_by_id 按 EntryId 清除所有历史位置；附件池可能在 tracked 快照登记前被删除。已用公开 API 重现，测试只确认悬空引用，不解引用或保存损坏状态。下一切片优先覆盖删除、同名替换、共享附件和历史独占引用，再修复生命周期；不靠重开重建来补救已经删除的内容。
- **跨类型混排仍改变。** XML Group 的 children 本来保留 Group/Entry 顺序；后续进入数据库模型并写出时失序。下一步检查分开的组/条目集合、增删移动及重组路径，不能误称 XML 解析器先拆成两个数组，也不能只调换输出数组。
- **_merge 未启用。** 上游 src/db/merge.rs 的排序和 latest 访问仍采用“最新在前”，与本实验追加契约不同。启用前必须统一合并顺序、最新项选择及引用重建；当前补丁不声称适用于全部 feature。
- 原有不存在的 CustomIconUUID 过滤行为未改变；历史裁剪/清空及其它资源删除路径尚未完整验证。未知 XML、未引用附件池、旧格式原样写回、资源预算、取消/崩溃/并发保存、Web/iOS/真机和多来源样本仍未达到生产门槛。

K009 继续负责发行许可证与旧库只读/显式升级策略。K001/K002/K068 的 REVIEW 与 K069 的 DOING 不变。回退只需撤销本实验目录、对应测试及说明增量；原 helper、锁文件、固定 KDBX、manifest、oracle 与真实用户资料均未改变。
