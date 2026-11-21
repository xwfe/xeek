# 云端开发交接

更新：2026-11-21。仓库：[xwfe/xeek](https://github.com/xwfe/xeek)，产品名 **keex**，默认开发分支 `main`。本次整理基于 `7f197cd`；接手时以实际 HEAD、未提交改动和权威任务状态为准，不从聊天摘要推断完成。

## 1. 接手入口与目录归属

先读 [AGENTS](../AGENTS.md)、[实施路线 §3](../adr/IMPLEMENTATION_PLAN.md)、[TASKS](../adr/TASKS.md)、[ADR-0008](../adr/0008-nsh-unified-clients.md) 与 [真实数据规则](../adr/REAL_DATA_RULES.md)。TASKS 是任务状态唯一入口，STATUS 记录进展与历史；本文件只说明如何接手和运行，不另建任务表。

| 位置 | 用途 |
| --- | --- |
| `AGENTS.md` | 中文、五导航、KDBX、安全边界与协作约定 |
| `docs/` | 开发者与云端接手操作说明 |
| `adr/` | 既有架构、产品/领域规格、实施计划、任务与验收 |
| `adr/evidence/` | 每项实验/任务的输入、命令、结果和缺口 |
| `adr/design/` | 原始设计与中文交互原型 |
| `tests/` | 合成样本、oracle、领域契约、候选与平台实验，见[索引](../tests/README.md) |
| `scripts/` | 不依赖特定代理工具的仓库检查入口 |

当前没有根 Cargo workspace 或生产应用；不要在仓库根直接猜测 `cargo test`、`npm install` 或启动命令。现有 Rust 核心仍在 `tests/wasm_core/` 的合成实验内。生产目录由 K010 定版，不提前创建空架构。

保留原始设计、fixture 和历史候选原路径：原稿摘要、样本清单与秘密扫描批准均绑定路径/字节。不要为“整理”移动目录、自动重算摘要，或把全部 `tests/` 当可删除临时文件。Git 已排除 SDK、依赖缓存和构建产物，克隆不会带上原机的这些条件。

## 2. 干净环境的最小检查

需要 Git、Python 3.12+、操作系统时区数据库（tzdata）。以下命令只使用 Python 标准库，不安装依赖、不调用浏览器或原生 SDK，也不要求 GLD：

```sh
git status --short --branch
git rev-parse HEAD
python3 -B scripts/check.py
```

检查入口固定执行现有三项文档/导航/任务依赖校验，以及领域 `test_contract.py`。子进程使用隔离模式和标准库，任一检查失败就返回非零；不会把失败改成跳过。成功仅证明这四组基线检查通过，不代表 writer、NSH、原生系统凭据或 Web 安全验证完成。

完整测试按 [tests/README.md](../tests/README.md) 选择。oracle、Rust、Dart、浏览器和秘密扫描有各自依赖/锁文件；首次下载需遵守当前执行环境的权限。现有 Python 哈希锁主要验证于 macOS arm64，不能宣称已覆盖 Linux；不得删除哈希、刷新样本或降低验收以让云端变绿。

平台脚本中仍有 Darwin/本机工具前提。云端可完成源码、契约、构建准备与可运行的合成测试；macOS/iOS/Windows、Android 真机、签名、系统输入/读屏、Safari 等证据必须在对应环境执行。缺失时记录具体未运行项与解除条件，不用交叉编译替代真机结果。

## 3. 下一项：K090

现行目标是 NSH + TSX 主 UI、共享 Rust，四原生端与独立 Web；停止扩大 Flutter/ForUI 生产 UI，保留旧实验作为对照。完整决定与验收见 ADR-0008、TASKS 和 ACCEPTANCE，不在此复制。

K090 的最小交付：

1. 核对候选 NSH v0.6.1 的完整 commit、CLI/运行时/绑定及依赖版本，登记来源和许可证；不要无记录追随主分支。
2. 明确主 UI/宿主最小 capabilities，核对四原生端与 Web 的构建前提、已有工具和资源缺口；只做当前环境能验证的部分。
3. 将实际命令、版本、结果、未运行项和下一步写入 `adr/evidence/K090.md`，再更新主任务状态。

K001/K002/K068 的人工 REVIEW 未通过；可做不依赖其结论的准备，不能视为门槛已满足。K090 未完成不提前扩大到四端生产工程。K091–K094 的 GN 迁移评审和 K009 writer 裁决分别保留；当前只用 L0 合成数据。iOS 仍按既有安排暂停，不因换执行环境自动恢复或标记通过。

## 4. 交付与提交

用执行环境实际可用的文件、终端和 Git 工具；本机 GLD 只是工具入口，不是项目依赖。克隆不会携带本机 `.git/config`、hooks、缓存、运行会话或设备授权。

每批只领取一个明确任务/平台切片，完成相关实现和必要验证后提交。提交前核对 diff、样本与真实数据边界，并按 [扫描说明](../tests/secret_scan/README.md) 检查完整暂存树；扫描依赖缺失或平台未验证时不能声称已通过，也不能绕过 hook。

提交身份按 AGENTS 的仓库级 `xwfe` / GitHub noreply 约定核对，不沿用云宿主默认个人邮箱。历史提交已按此身份统一；不要再次改写历史。推送权限、目标分支与分支保护按当前授权处理；本次历史统一不授权未来代理任意发布、部署或强制推送。未通过的安全/兼容门槛仍由独立审查决定。

## 5. 可直接交给云端模型的任务

> 在当前克隆中读取 AGENTS.md 和 docs/CLOUD_HANDOFF.md，核对 main/HEAD、工作树与 adr/TASKS.md，运行 python3 -B scripts/check.py。随后只推进 K090：固定 NSH 候选及依赖/许可证，核对最小宿主权限和四原生端/Web 构建资源，形成 adr/evidence/K090.md。沿用 NSH + TSX + Rust 与既有 KDBX/五导航契约，复用现有样本和实验，不扩大 Flutter UI。可做依赖未批准时的独立准备，但不跳过 REVIEW/GN/G0，不使用真实数据；无法执行的平台记录阻塞。完成本批实际验证后同步 TASKS/STATUS，按项目约定提交，推送与发布遵守当前授权。
