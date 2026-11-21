# keex

中文优先、本地优先的个人数据保险柜，以 KeePass KDBX 管理密码、验证凭据、证件、银行卡/金融账户、SIM/eSIM、订阅与维护事项。

A local-first personal data vault built around KeePass KDBX.

产品名为 **keex**，代码仓库为 [xwfe/xeek](https://github.com/xwfe/xeek)。目标架构：**NSH + TSX + Rust**，覆盖 Android、iOS、macOS、Windows 与独立验收的 Web。

**当前是 P0 合成实验，尚无生产客户端。** writer 闸门关闭，NSH 任务从 K090 开始；实时进度以 [任务表](adr/TASKS.md) 和 [状态记录](adr/STATUS.md) 为准。

## 使用场景

集中查找资料，换卡前核对关联扣费，停号前检查验证/恢复账户，管理证件、套餐与订阅到期。首版只管理资料和用户确认的维护事项，不执行转账、充值或 eSIM 安装。

## 开发与云端接手

先读 [项目契约](AGENTS.md) 和 [云端交接](docs/CLOUD_HANDOFF.md)。克隆后使用 Python 3.12+ 与系统时区数据运行无额外依赖的基线检查：

```sh
python3 -B scripts/check.py
```

[实施路线](adr/IMPLEMENTATION_PLAN.md) · [NSH 决策](adr/0008-nsh-unified-clients.md) · [实验与测试索引](tests/README.md) · [完整文档索引](adr/README.md)

## 查看交互原型

```sh
python3 -m http.server 5173 --bind 127.0.0.1 --directory adr/design/zh-CN
```

打开本机 5173 端口；iOS 专项稿为 `/ios.html`。原型只有演示数据，不具备加密或系统凭据能力。设计说明见 [设计基准](adr/design/README.md)。

## 使用边界

只用合成资料开发；不要向原型输入真实秘密。KDBX 是唯一权威库；同步和浏览器缓存不是备份。各端能力与真实数据准入必须按 [验收标准](adr/ACCEPTANCE.md) 和 [真实数据规则](adr/REAL_DATA_RULES.md) 分别通过。
