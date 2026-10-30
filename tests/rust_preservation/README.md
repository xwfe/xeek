# Rust 保留补丁实验

K003 的隔离实验：在 keepass 0.15.3 上保留标准/自定义图标双字段，将编辑前快照追加到历史末尾，让删除或替换附件只释放当前版本的引用，按 KeePass/KeePassXC 的顺序先写条目、后写子组，对模型带不过去的 XML 拒绝保存或拒绝打开，让 tracked 编辑按库里的上限裁剪历史，并且不改变文件没写的元素的含义。只处理公开合成数据；生产写入闸门仍关闭。

## 构建与回归

从仓库根目录执行，复用已有 Cargo、Python、KeePassXC 和固定缓存：

~~~sh
python3 -B tests/rust_preservation/build.py
python3 -B tests/run_python_tests.py --suite oracle --pattern test_rust_preservation.py -v
python3 -B tests/run_python_tests.py --suite oracle --pattern test_rust_history_trim.py -v
python3 -B tests/run_python_tests.py --suite oracle --pattern test_rust_third_party.py -v
~~~

第一条离线构建补丁 helper 并运行 Rust API 测试；第二条还运行微型输入和原 12 项算法矩阵，使用独立 oracle 检查完整输出并由 KeePassXC 重开；第三条让补丁库和 KeePassXC 编辑同一份输入，对照历史裁剪结果；第四条让补丁库和 KeePassXC 轮流改同一份文件，每一步全文比较。缺工具、缓存、源码哈希不符或补丁失败均直接报错。

[build.py](build.py) 从原 [Cargo.lock](../reference_writer/Cargo.lock) 读取版本与校验和，核对缓存中的 crate 归档，再解包到临时目录，按顺序应用：

1. [01-icons.patch](patches/01-icons.patch)：模型明确表示两个图标字段共存，贯通 XML 读写、查询与引用清理。
2. [02-history.patch](patches/02-history.patch)：追加新快照并登记它的图标/附件引用，保持旧历史索引稳定；重开时重建当前与历史的附件反向引用。
3. [03-attachments.patch](patches/03-attachments.patch)：删除附件只去掉“这一个版本”的引用，其它历史版本或条目还在用时保留内容；tracked 编辑开始时就把编辑前快照追加进历史并登记引用，所以编辑中删除或同名替换附件不会先把快照要用的内容删掉。
4. [04-child-order.patch](patches/04-child-order.patch)：同一分组下先写条目、后写子组。KeePass 和 KeePassXC 都把两者存成两个列表并这样写出，所以它们写的文件顺序不变；它们自己也表示不了的交错顺序，同样被规范成这个顺序。
5. [05-unknown-content.patch](patches/05-unknown-content.patch)：解析前按模型实际支持的元素表扫描解密后的 XML。有未知元素、属性或游离文字时可读但 `save` 报错，路径由 `Database::unknown_content()` 给出（只含元素名，不含值）；未知内容带受保护值，或文档顺序与解密顺序不一致时拒绝打开。
6. [06-history-limits.patch](patches/06-history-limits.patch)：tracked 编辑按 `HistoryMaxItems`/`HistoryMaxSize` 裁剪这一个条目的历史，保留最新的版本，并同步附件/图标引用；只有被删版本用的附件内容随之删除。另加 `EntryMut::trim_history()`（调低上限后用）和 `clear_history()`。不要直接给公开字段 `entry.history` 赋值：附件内容会留在文件里，遍历引用还会 panic。
7. [07-absent-defaults.patch](patches/07-absent-defaults.patch)：文件没写 `QualityCheck` 时保持没写（KeePass/KeePassXC 只在值为 false 时才写，上游会给每个条目补 `True`）；没写 `IsExpanded` 时按展开读（两个客户端的默认值，上游读成折叠）。

实验 manifest 直接引用原 helper 源码。临时锁只改实验根包名和 keepass 来源，传递版本/校验和保持原锁；构建使用 `--locked --offline`。原候选源码、锁文件、包缓存、样本与 manifest 不被修改。固定上游部分遵循 [MIT 许可证](LICENSE.keepass)，不决定 keex 产品的发行许可。

## 产物与边界

补丁二进制为 `tests/reference_writer/target/release/keex-preservation-writer`；原 `keex-reference-writer` 保留。它要求历史恰好多一份，真发生裁剪时返回 `model_count_mismatch`，所以裁剪对照用单独的 `keex-history-edit`（[源码](src/history_edit.rs)）。二者复用 Cargo 构建缓存，名称独立。解包源码和测试密码库只放本实验 `target/` 下的临时目录，正常结束或异常时自动清理，不提交生成的 KDBX。

测试按“仅编辑目标 UserName、更新修改时间、追加一份完整旧快照”的契约比较全文，历史容器不作为忽略项。Rust 双图标测试从既有合成生成器创建临时输入，经公开 API 读取。原 12 组矩阵按全文比较已无差异；构造的交错顺序只断言“条目在前、子组在后、各自相对顺序不变”。

Rust API 测试另用登记过的 v41-vault-edit1 样本（构建时先核对 vault_manifest 中的哈希）覆盖共享附件和只在历史里出现的附件。Rust API 测试还会打开全部登记样本，确认扫描表不会误拦真实客户端写的文件。_merge 未启用，其历史排序契约未调整。旧格式写入、未知扩展及其余限制见 [补丁证据](../../adr/evidence/K003_RUST_PATCH.md)。

补丁不直接应用于系统缓存，也不接入客户端；升级候选版本时须重新核对来源、调用链与全部回归。
