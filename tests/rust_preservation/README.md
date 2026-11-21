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
8. [08-edit-times.patch](patches/08-edit-times.patch)：tracked 编辑的修改时间严格晚于被替换的版本。同一秒内连续编辑时取前一版加 1 秒，否则 KeePassXC 合并时会把时间相同的历史当成一份丢掉。

实验 manifest 直接引用原 helper 源码。临时锁只改实验根包名和 keepass 来源，传递版本/校验和保持原锁；构建使用 `--locked --offline`。原候选源码、锁文件、包缓存、样本与 manifest 不被修改。固定上游部分遵循 [MIT 许可证](LICENSE.keepass)，不决定 keex 产品的发行许可。

## 产物与边界

补丁二进制为 `tests/reference_writer/target/release/keex-preservation-writer`；原 `keex-reference-writer` 保留。它要求历史恰好多一份，真发生裁剪时返回 `model_count_mismatch`，所以裁剪对照用单独的 `keex-history-edit`（[源码](src/history_edit.rs)）。二者复用 Cargo 构建缓存，名称独立。解包源码和测试密码库只放本实验 `target/` 下的临时目录，正常结束或异常时自动清理，不提交生成的 KDBX。

测试按“仅编辑目标 UserName、更新修改时间、追加一份完整旧快照”的契约比较全文，历史容器不作为忽略项。Rust 双图标测试从既有合成生成器创建临时输入，经公开 API 读取。原 12 组矩阵按全文比较已无差异；构造的交错顺序只断言“条目在前、子组在后、各自相对顺序不变”。

Rust API 测试另用登记过的 v41-vault-edit1 样本（构建时先核对 vault_manifest 中的哈希）覆盖共享附件和只在历史里出现的附件。Rust API 测试还会打开全部登记样本，确认扫描表不会误拦真实客户端写的文件。_merge 未启用，其历史排序契约未调整。旧格式写入、未知扩展及其余限制见 [补丁证据](../../adr/evidence/K003_RUST_PATCH.md)。

补丁不直接应用于系统缓存，也不接入客户端；升级候选版本时须重新核对来源、调用链与全部回归。

## 官方 KeePass 2.62 与 `_merge` 独立准备

只读取已登记 L0 输出（无需 Mono）：

~~~sh
python3 -B tests/run_python_tests.py --suite oracle --pattern test_official_keepass.py -v
python3 -B tests/rust_preservation/merge_probe.py
~~~

官方来源、Linux 用户级 Mono 依赖和实测输出见 [K003 追加证据](../../adr/evidence/K003.md)。[official.kps](official.kps) 通过官方 KPScript 访问 KeePassLib API，不把 GPL KeePass 链入 keex。先用现有 `build.py` 构建隔离补丁 helper，再于**不含本批样本/清单的独立实验工作树**生成：

~~~sh
python3 -B tests/rust_preservation/build.py
python3 -B tests/rust_preservation/official_roundtrip.py generate --tools "$HOME/k090-logs/k003-official" --mono-root "$HOME/.local/mono-k003"
~~~

工具目录须预先放入官方 `KeePass-2.62.zip`、`KPScript-2.62.zip`，并解包到其 `keepass-2.62/` 子目录；生成器先核对固定官网哈希及解包 EXE，调用 Xvfb，不联网、不覆盖。已有清单或任一输出时直接拒绝；新随机库不能替换本次已登记文件。普通异常清理仅限本次创建的文件，不承诺强杀/掉电恢复。回归只需读取固定文件；完整现场重跑需另起独立实验，审查新的来源/差异后另行登记。

严格 oracle 没有被改动：Rust 输出的根组 `EnableAutoType`/`EnableSearching` 为小写 `null`，官方写作 `Null`；每腿两项原始差异完整登记。诊断只识别这两个路径的这两种精确拼写，其余差异仍失败；测试另断言严格比较确实拒绝、漏编辑/空结果/额外改动/错误密码均被拒绝。官方重开时检查两个设置的 `HasValue` 都为 false，不能用这里的有限表示分析宣称整个候选已无损。

`merge_probe.py` 校验原 Cargo.lock 的 keepass 0.15.3 归档，在隔离临时 manifest **仅启用原版 `_merge`**，不应用八补丁，不改变现有依赖/锁/生产 features。读取新登记的官方合成样本，四项诊断覆盖 no-op、同时间当前条目冲突报错、新源无历史时目的旧快照丢失、新源附件不应用。通过表示两个缺陷被复现，不是合并安全通过。补丁与 `_merge` 的联合构建/保存、历史同时间警告与去重、自定义图标和删除/移动仍待验证；写入闸门关闭。
