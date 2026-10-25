# keex

中文优先、本地优先的**个人数据保险柜**。以 KeePass KDBX 统一管理密码、验证凭据、证件、金融账户、实体/虚拟卡、SIM/eSIM、订阅及维护事项，保证 KeeAgent 数据无损。目标为 **Android、iOS 与独立验收的 Web 客户端**；移动界面采用 Flutter，Web 优先复用，原生桌面仍留给未来 Rust 应用。

**当前阶段：P0 风险实验。** 只有方案、HTML 交互原型和合成测试工具，尚无可用的 Flutter/Web 客户端或生产安全核心。两个 KDBX 写入候选在同一批合成库上都没做到无损，写入闸门关闭。现状与卡点见 [STATUS](adr/STATUS.md)，任务状态见 [TASKS](adr/TASKS.md)。HTML 原型仅含演示数据，不保存输入、不接入系统凭据服务。

主要场景：集中查找资料；换卡前找出关联扣费；停号前检查验证/恢复账户；管理证件、套餐与订阅到期。只管理资料和用户确认的状态，不执行转账、充值或 eSIM 安装。

## 查看设计

直接打开 `adr/design/zh-CN/index.html`；也可在项目根目录运行：

```sh
python3 -m http.server 5173 --bind 127.0.0.1 --directory adr/design/zh-CN
```

浏览器打开本机 5173 端口。支持五项导航、条目详情、筛选/搜索、深浅主题、锁定演示和新增流程说明。关闭终端中的服务即可停止预览。

iOS 专项交互稿：`adr/design/zh-CN/ios.html`，补充双云同步、系统凭据请求、高级属性和附件流程。模拟版本选择仅用于设计预览，不是设备能力检测。

移动体验参考 Bitwarden：已补充合成条目的搜索范围、收藏/分组筛选、模板选择、编辑布局和更多操作；规则与后续验收见 [移动体验基线](adr/design/BITWARDEN_MOBILE_REFERENCE.md)。

## 开发入口

- [设计说明与原稿修正](adr/design/README.md)：中文术语、导航、状态、响应式布局。
- [个人数据保险柜决策](adr/0006-personal-data-vault.md)、[领域规格](adr/PERSONAL_VAULT_SPEC.md)、[专项实施与交接](adr/PERSONAL_VAULT_PLAN.md)：类型、关联、维护闭环及新增 K068–K089。
- [Web 客户端决策](adr/0007-web-vault-client.md)：独立存储、授权、同步与安全门槛；[基础架构](adr/0001-flutter-kdbx-architecture.md)、[未来 Rust 桌面边界](adr/0005-mobile-first-scope.md)。
- [威胁模型](adr/THREAT_MODEL.md)、[能力状态与平台矩阵](adr/CAPABILITIES.md)、[真实数据使用规则](adr/REAL_DATA_RULES.md)：K001 交付，待独立复核。
- [KDBX 合成样本](tests/fixtures/kdbx/README.md)与[测试对照工具](tests/kdbx_oracle/README.md)：K002 交付与比较器修正，待独立复核。 [固定依赖与参考保存实验](adr/evidence/K002_LIBRARIES.md)记录当前实现、差异和复跑方法。 [4.x 负载与资源边界](adr/evidence/K002_RESOURCES.md)记录认证负载反例与读取器修复；回归入口与当前数量见测试对照工具说明。
- [写入候选对照](adr/evidence/K003.md)：keepass-rs 与 kdbx.dart 同样本读改写预实验（K003），Dart helper 见 [tests/dart_candidate](tests/dart_candidate/README.md)。
- [字段契约 v1](adr/K068_FIELD_CONTRACT.md)与[领域测试入口](tests/vault_domain/README.md)：类型、关系、日期、手工事实及未知数据的可执行合成规格；不是生产写入实现。
- [提交前秘密与合成样本扫描](tests/secret_scan/README.md)：完整暂存区检查、精确样本登记、脱敏输出；支持显式安装本仓库 pre-commit，见[扫描证据](adr/evidence/K002_SECRETS.md)和[提交接入验收](adr/evidence/K002_HOOKS.md)。
- [实施路线](adr/IMPLEMENTATION_PLAN.md)、[任务清单](adr/TASKS.md)、[验收标准](adr/ACCEPTANCE.md)。
- [调研依据](adr/RESEARCH.md)、[当前状态与历史记录](adr/STATUS.md)；全部文档与证据索引见 [adr/README.md](adr/README.md)。
- [iOS/Android 系统凭据](adr/0002-mobile-credentials.md)、[WebDAV/OneDrive](adr/0003-cloud-sync.md)、[高级 KDBX/Passkey](adr/0004-kdbx-advanced-passkeys.md)；[24 项专项子任务](adr/MOBILE_SYNC_TASKS.md)。

## 使用边界

新库目标为 KDBX 4.1，不要求 keex 账户或业务后端。同步是可选密文传输，Web 仍需可信静态部署；浏览器缓存不是备份，文件导出不是自动写回，余额/服务状态不冒充实时结果。忘记主密码且无其他有效密钥材料时不能承诺恢复。不要向原型输入真实资料。
