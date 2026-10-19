# keex

中文优先、本地优先的移动端（iOS/Android）密码管理器。以 KeePass KDBX 为密码库，用 Flutter 做界面，规划支持密码、动态口令、通行密钥、证件、银行卡，并保证 KeeAgent（SSH 密钥）数据不被弄坏。桌面端留给未来用 Rust 开发的应用，见 [ADR-0005](adr/0005-mobile-first-scope.md)。

**当前阶段：设计修订与实施规划。** 目录中尚无 Flutter 应用或可用于真实密码的安全核心。HTML 原型仅含演示数据，不保存输入、不接入系统凭据服务。

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
- [架构决策](adr/0001-flutter-kdbx-architecture.md)：KDBX、Rust 候选核心、系统扩展、同步与安全边界；[范围收窄为移动端](adr/0005-mobile-first-scope.md)。
- [威胁模型](adr/THREAT_MODEL.md)、[能力状态与平台矩阵](adr/CAPABILITIES.md)、[真实数据使用规则](adr/REAL_DATA_RULES.md)：K001 交付，待独立复核。
- [KDBX 合成样本](tests/fixtures/kdbx/README.md)与[测试对照工具](tests/kdbx_oracle/README.md)：K002 交付，待独立复核。只用于测试，不是 keex 的实现。
- [提交前秘密与合成样本扫描](tests/secret_scan/README.md)：完整暂存区检查、精确样本登记、脱敏输出；[本轮证据](adr/evidence/K002_SECRETS.md)记录失败回归与验收边界。
- [实施路线](adr/IMPLEMENTATION_PLAN.md)、[任务清单](adr/TASKS.md)、[验收标准](adr/ACCEPTANCE.md)。
- [调研依据](adr/RESEARCH.md)、[当前状态与验证](adr/STATUS.md)。
- [iOS/Android 系统凭据](adr/0002-mobile-credentials.md)、[WebDAV/OneDrive](adr/0003-cloud-sync.md)、[高级 KDBX/Passkey](adr/0004-kdbx-advanced-passkeys.md)；[24 项专项子任务](adr/MOBILE_SYNC_TASKS.md)。

## 使用边界

新库目标为 KDBX 4.1，不要求账户或自建服务器。WebDAV 等同步属于可选密文文件传输。忘记主密码且无其他有效密钥材料时不能承诺恢复。不要向演示稿输入真实密码、私钥或证件数据。
