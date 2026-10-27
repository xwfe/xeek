# Rust 保留补丁实验

K003 的隔离实验：在 keepass 0.15.3 上保留标准/自定义图标双字段，并将编辑前快照追加到历史末尾。只处理公开合成数据；生产写入闸门仍关闭。

## 构建与回归

从仓库根目录执行，复用已有 Cargo、Python、KeePassXC 和固定缓存：

~~~sh
python3 -B tests/rust_preservation/build.py
python3 -B tests/run_python_tests.py --suite oracle --pattern test_rust_preservation.py -v
~~~

第一条离线构建补丁 helper 并运行 Rust API 测试；第二条还运行微型输入和原 12 项算法矩阵，使用独立 oracle 检查完整输出并由 KeePassXC 重开。缺工具、缓存、源码哈希不符或补丁失败均直接报错。

[build.py](build.py) 从原 [Cargo.lock](../reference_writer/Cargo.lock) 读取版本与校验和，核对缓存中的 crate 归档，再解包到临时目录，按顺序应用：

1. [01-icons.patch](patches/01-icons.patch)：模型明确表示两个图标字段共存，贯通 XML 读写、查询与引用清理。
2. [02-history.patch](patches/02-history.patch)：追加新快照并登记它的图标/附件引用，保持旧历史索引稳定；重开时重建当前与历史的附件反向引用。

实验 manifest 直接引用原 helper 源码。临时锁只改实验根包名和 keepass 来源，传递版本/校验和保持原锁；构建使用 `--locked --offline`。原候选源码、锁文件、包缓存、样本与 manifest 不被修改。固定上游部分遵循 [MIT 许可证](LICENSE.keepass)，不决定 keex 产品的发行许可。

## 产物与边界

补丁二进制为 `tests/reference_writer/target/release/keex-preservation-writer`；原 `keex-reference-writer` 保留。二者复用 Cargo 构建缓存，名称独立。解包源码和测试密码库只放本实验 `target/` 下的临时目录，正常结束或异常时自动清理，不提交生成的 KDBX。

测试按“仅编辑目标 UserName、更新修改时间、追加一份完整旧快照”的契约比较全文，历史容器不作为忽略项。Rust 双图标测试从既有合成生成器创建临时输入，经公开 API 读取。已知组/条目混排差异仍须明确观察，不能解释为无损通过。

附件删除导致历史悬空的 known_gap 测试明确复现未修缺陷，不代表生命周期通过；_merge 未启用，其历史排序契约未调整。旧格式写入、未知扩展及其余限制见 [补丁证据](../../adr/evidence/K003_RUST_PATCH.md)。

补丁不直接应用于系统缓存，也不接入客户端；升级候选版本时须重新核对来源、调用链与全部回归。
