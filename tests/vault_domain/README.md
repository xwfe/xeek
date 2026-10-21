# 个人资料合成契约与 KDBX 样本

这里是 K068/K069 的测试规格，不是生产业务核心或第二个密码库。完整字段契约见 [K068_FIELD_CONTRACT](../../adr/K068_FIELD_CONTRACT.md)，唯一字段字典为 [contract.json](contract.json)。

## 执行

仓库根目录：

~~~sh
python3 -B -m unittest discover -s tests/vault_domain -p test_contract.py
python3 -B tests/run_python_tests.py --suite domain
~~~

第一条契约测试只需要 Python 标准库和系统时区数据；第二条运行当前全部 93 项领域测试，复用 oracle、固定测试依赖和 KeePassXC 对照。较早结果见 [K068](../../adr/evidence/K068.md) / [K069](../../adr/evidence/K069.md)，本轮项目内 Argon2 后端与固定 Rust 参考实验见 [K002_LIBRARIES](../../adr/evidence/K002_LIBRARIES.md)。

## 读取检查结果

- valid：合成条目的已知字段符合 v1；不表示可写 KDBX、已授权或生产能力通过。
- legacy：没有领域 marker 和未知 keex 字段的旧条目；允许旧 parent 别名，保持原始值和混合凭据。
- read_only：未知/畸形/冲突数据保留原样，不修改输入。
- warning：缺失目标、未知到期依据等不能被当作已确定的业务事实。

错误只返回问题码，不回显字段值。Protected 不符合字典时更严格地限制显示，不自动改写保护属性。record_from_pairs 在 XML 字段转 map 前拒绝重复 Key。

## 样本

源 XML 确定性生成，已有 K002 黄金文件和 manifest 保持原样。领域库及清单位于 tests/fixtures/kdbx/：

- vault_source.py：在原 rich 源上加入 24 条资料，覆盖 13 种类型、关系、规则、历史与未来字段。
- vault_generate.py：调用现有 KeePassXC；默认不覆盖样本，临时文件只含合成数据。
- vault_manifest.json：三种格式各导入/编辑1/编辑2，共九份库的来源、哈希、摘要及各阶段差异；原生成版本与后续比较策略版本分别记录。

新增 matrix_source / matrix_generate / matrix_checks / matrix_probe 与 matrix_manifest.json，另有17份同 RP 多 Passkey及精确1k/10k规模库。内容、资源与失败边界见 [K069_MATRIX](../../adr/evidence/K069_MATRIX.md)。另有 12 份固定 Rust 参考保存输出，三种 KDF × 两种外层密码分别覆盖同 RP 与领域输入；字段/历史/附件保留通过，但剩余语义差异没有豁免。对应 15 项测试属于 oracle 入口，不计入本目录 93 项。

源 XML → 首次导入、每次单字段编辑及源 → 最终库分别比较；参考客户端自身变异单独记账，不能把丢失后的值洗成原始正确基线。K003 双候选 Rust/Dart writer、未覆盖参数、官方/移动多客户端及 Web 端仍有独立门槛；固定参考 helper 不代表生产选型。
