# K091 Windows：NSH Win32 宿主 + 同一 Rust 核心切片（未签名、虚拟机、仅 L0）

日期：2026-11-22。**K091 仍为 DOING；本文件只补 Windows 平台切片的实际运行记录，不代表 Android/iOS/macOS/Web 任一端通过，也不代表 Windows 已达生产或发布标准。** 运行环境是云端虚拟机而非真机；产物未签名；没有独立安全复核；只使用仓库内公开 L0 合成样本与公开合成口令。Linux-headless 证据见 [K091](K091.md)，固定输入见 [K090](K090.md)，复现入口见 [nsh_candidate README](../../tests/nsh_candidate/README.md) 的 Windows 小节。

基线：`devin/1795273556-k091-nsh-rust-slice` @ `2f27fc9`。NSH：`https://github.com/longbridge/nsh` tag v0.6.1，`git -C ~/nsh-k090 rev-parse HEAD` = `2f51d8611677c8a6bbad937b39756e8d0cc45350`，工作树干净；`nsh --version` 输出 `nsh 0.6.1 (2f51d86)`。

## 1. 结果一览

| 项 | 结果 | 说明 |
| --- | --- | --- |
| 固定提交 NSH CLI 构建 | 通过 | `cargo build --locked -p nsh-cli`，debug，6m22s |
| Rust 单测 | 通过 | debug 与 release 各 5 passed / 0 failed |
| 目录级 `nsh test --trace` | 通过 | 11 passed / 0 failed（5 项 Rust + 6 项 TSX，headless） |
| `oracle_check.py` | 修 2 行后通过 | 原样在 Windows 因 cp1252 解码失败；5 tests OK |
| `scripts/check.py` | 修 1 行并满足 3 个环境条件后通过 | 见 §4 平台假定清单 |
| Win32 release runner 实际启动并走完合成流程 | 通过（未签名包、虚拟机） | 基础/1k/10k 三份样本；鼠标键盘与纯键盘各一遍 |
| Win32 开发宿主 `nsh run` | 通过（debug） | 解锁、读单字段、锁库后旧句柄拒绝；未在开发宿主重复改/存 |
| Win32 副本的 oracle 对照 | 通过 | 四份 Win32 宿主写出的副本，三次运行均 5 tests OK |
| 中文显示（Text 标签、列表行） | 通过 | |
| 中文显示（Input 内） | **部分失败** | 非中文键盘布局下以合成 Unicode 按键注入的 CJK 显示为方框；IME/粘贴/UIA 赋值正常，见 §6 |
| 微软拼音 IME 输入 | 通过 | 组字、候选窗、上屏、搜索命中 |
| 纯键盘操作 | 通过，有缺口 | Tab/Shift+Tab/Enter/Space 可走完全流程；**无可见焦点指示** |
| 可访问性（UI Automation） | 部分通过 | 按钮有名称与 Invoke；**三个输入框无可访问名称** |
| 讲述人朗读 | **BLOCKED** | 无声音设备、无中文 TTS；只观察到讲述人焦点框跟随 |
| `NSH_APP_DIR` 覆盖入口 | **仍然生效（风险确认）** | release runner 会改载外部未签名 bundle 及其 capabilities，见 §7 |
| 1k/10k 耗时 | 已记录 | 仅观测，不是性能门槛结论，见 §9 |
| 代码签名、安装包 | **BLOCKED** | 无证书；Inno Setup 未安装且未擅自安装 |
| 真机、高 DPI/多显示器、触摸、Windows 10/11 桌面版 | 未做 | 无设备 |

## 2. 机器与构建条件

机器：cloud-hypervisor 虚拟机，Windows Server 2022 Standard 21H2（10.0.20348），Intel Xeon Platinum 8559C 8 逻辑处理器，约 32 GB 内存，显示适配器 `IddSampleDriver Device` 1600×1200（虚拟显示，无实体 GPU 信息），`Win32_SoundDevice` 数量为 0。

盘点时已有：Python 3.13.12（`C:\Program Files\Python313`）、Git for Windows 2.47.1、Node 24.22.2、WSL Ubuntu 24.04（Python 3.12.3、Git 2.43.0）。**没有** Rust、MSVC Build Tools、Windows SDK、LLVM/libclang，也没有原生 Python 3.12。

本轮安装（均为构建必需）：

| 组件 | 版本 | 来源与校验 | 范围 |
| --- | --- | --- | --- |
| rustup / Rust | rustup 1.29.3；`1.100.0-x86_64-pc-windows-msvc`（minimal，`--no-modify-path`） | `https://win.rustup.rs/x86_64`，rustup-init.exe SHA-256 `38027d51d69a5d05493627a0634dbea52d6cd793c8f072d2373d3f4163eec7db` | 用户级 `~/.cargo`、`~/.rustup` |
| LLVM/libclang | 18.1.8 | LLVM 官方 GitHub release `clang+llvm-18.1.8-x86_64-pc-windows-msvc.tar.xz`，SHA-256 `22c5907db053026cc2a8ff96d21c0f642a90d24d66c23c6d28ee7b1d572b82e8`；只解出 `bin/libclang.dll`、`bin/clang.exe`、`lib/clang/` | 用户级 `~/.local/llvm18` |
| VS Build Tools 2022 | 17.14.37906.3；MSVC 14.44.35207；Windows SDK 10.0.22621.0 | `https://aka.ms/vs/17/release/vs_BuildTools.exe`，SHA-256 `8aaf70d164808d313ee6226af5d1e3b2db43c60be551bfeb2b70ce139d792c37`；参数 `--quiet --wait --norestart --nocache --add Microsoft.VisualStudio.Component.VC.Tools.x86.x64 --add Microsoft.VisualStudio.Component.Windows11SDK.22621` | **全局安装**（该安装器不支持用户级）；受 Visual Studio 许可条款约束，是否符合使用方的许可条件须由使用方自行确认；安装前已在会话中告知 |
| tzdata | 2026.1 | PyPI wheel，SHA-256 `4b1d2be7ac37ceafd7327b961aa3a54e467efbdb563a23655fbfe0d39cfc42a9`，仅解压 | 用户级 `~/.local/tzdata` |
| oracle 依赖 | cryptography 46.0.4、argon2-cffi 25.1.0、argon2-cffi-bindings 26.1.0、cffi 2.1.1 | README 的 pip 命令，原生 Python 3.13.12 | 项目内已忽略的 `tests/kdbx_oracle/.deps-argon2` |
| 秘密扫描依赖 | 按 `requirements.lock` 哈希锁 | WSL Ubuntu 内 `pip.pyz`（bootstrap.pypa.io）`--require-hashes` | 项目内已忽略的 `tests/secret_scan/.deps` |

未安装：原生 Python 3.12（3.13.12 满足“3.12+”，README 中的 `python3.12` 命令名在本机不存在，改用 `python`）、Inno Setup、任何签名工具或证书。

为做 IME 检查，曾用 `Set-WinUserLanguageList` 在用户级语言列表临时加入 `zh-Hans-CN`（微软拼音）；检查后已恢复为只有 `en-US`（`0409:00000409`），与盘点时一致。

统一环境（Git Bash）：

```sh
export PATH="$HOME/.cargo/bin:$PATH" RUSTUP_TOOLCHAIN=1.100.0-x86_64-pc-windows-msvc
export LIBCLANG_PATH='C:\Users\Administrator\.local\llvm18\bin'
export PYTHONTZPATH='C:\Users\Administrator\.local\tzdata\tzdata\zoneinfo'
```

## 3. 固定提交 NSH CLI

```sh
git clone --branch v0.6.1 --depth 1 https://github.com/longbridge/nsh "$HOME/nsh-k090"
cd "$HOME/nsh-k090" && cargo build --locked -p nsh-cli
```

结果：debug 构建成功，6m22s。未改动 NSH 源码。

## 4. 复跑检查与脚本平台假定

```sh
cargo test --locked --manifest-path tests/nsh_candidate/rust/Cargo.toml --lib -- --nocapture --test-threads=1
cargo test --release --locked --manifest-path tests/nsh_candidate/rust/Cargo.toml --lib -- --nocapture --test-threads=1
CARGO_TARGET_DIR="$HOME/nsh-k090/target" "$HOME/nsh-k090/target/debug/nsh.exe" test "$PWD/tests/nsh_candidate" --trace
python -B tests/nsh_candidate/oracle_check.py
python -X utf8 -B scripts/check.py
```

```text
# Rust 单测 debug
test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 17.68s
# Rust 单测 release
test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.84s
# nsh test 目录级（含首次构建共 6m09s）
✓ 11 tests: 11 passed, 0 failed (4m 55s)
# oracle_check.py（headless 副本，修复后）
Ran 5 tests in 13.512s
OK
# scripts/check.py（原生 Windows，最终复跑）
Ran 63 tests in 0.022s
OK
4 组基线检查通过；不代表生产或平台能力验收。
```

`nsh test` 仍输出 `statusBar` 未授权告警，这是显式 `"capabilities": {}` 生效的表现；`nsh.json` 未改动，未为消除告警扩大能力。

遇到的 Unix/macOS 假定，按出现位置记录：

| 位置 | Windows 上的现象 | 处理 |
| --- | --- | --- |
| `scripts/check.py` 子进程参数 `-I -S -B` | 隔离模式忽略 `PYTHONUTF8`，子脚本 `read_text()` 用 cp1252，`UnicodeDecodeError`（`adr/design/verify.py:26`） | **已修 1 行**：子进程加 `-X utf8` |
| `scripts/check.py:24` 父进程 `print` | 输出被重定向时 cp1252 无法编码中文，`UnicodeEncodeError` | 未改代码；用 `python -X utf8` 运行 |
| `adr/design/verify.py:17` 摘要核对 | Git for Windows 默认 `core.autocrlf=true`，检出为 CRLF，登记的 SHA-256 不符 | 未改代码、未改 Git 配置；用 `git -c core.autocrlf=false checkout-index --all --force` 得到 LF 工作树 |
| `tests/vault_domain/test_contract.py` | Windows 无系统 IANA 时区库，13/63 失败 `unknown_timezone` | 未改代码；用户级解压 tzdata 并设置 `PYTHONTZPATH` |
| `tests/nsh_candidate/oracle_check.py:55,61` | `read_text()` 按 cp1252 读 UTF-8 JSON，`UnicodeDecodeError`，0 项测试运行 | **已修 2 行**：`encoding="utf-8"` |
| `tests/wasm_core/build.py:49` | `--directory=` 传入反斜杠路径，`git apply` 报 invalid path | **已修 1 行**：`.as_posix()` |
| `tests/secret_scan/hooks.py` | `status`/`install` 均返回 `{"code": "UNSUPPORTED_PLATFORM"}`，rc=2；`requirements.lock` 无 Windows wheel 哈希 | 未改；按其设计在 WSL（已验证的 Linux x86_64 / CPython 3.12）安装 hook 并从 WSL 提交 |
| `~/nsh-k090/rust-toolchain.toml` | `channel = "stable"` 加 Apple/Android targets，会触发滚动 stable 与多个交叉 target 下载 | 未改 NSH；用 `RUSTUP_TOOLCHAIN` 固定 1.100.0 |
| README 的 `python3.12`、`nsh` 命令名 | 本机为 `python`、`nsh.exe` | 复现小节给出 Windows 写法 |
| Git Bash 的 `tar` | PATH 中先命中 `System32\tar.exe`（bsdtar） | 解包时用 `/usr/bin/tar` |

三处代码修正后在 WSL Ubuntu（Python 3.12.3）复跑 `python3 -B scripts/check.py`：63 tests OK，rc=0，Linux 路径未回归。

## 5. Win32 宿主实际运行

未签名 release runner：

```sh
CARGO_TARGET_DIR="$HOME/nsh-k090/target" "$HOME/nsh-k090/target/debug/nsh.exe" package "$PWD/tests/nsh_candidate" --target windows -o "$HOME/k091-win/pkg"
```

```text
✓ built the release runner for Windows (3m 42s)
✓ packaged C:/Users/Administrator/k091-win/pkg\keex 合成实验 and C:/Users/Administrator/k091-win/pkg\keex 合成实验.zip (6.7s)
warn wrote C:/Users/Administrator/k091-win/pkg\keex 合成实验.iss but not the installer: install Inno Setup 6 ...
```

产物：`keex 合成实验.exe` 46,394,880 字节，SHA-256 `f3d19dd848cf7d9456d694646a541c42ba32067289b7a9621fdda1462eb8e04b`；zip SHA-256 `cd9644413f7cfe06d7ba7191c85cbff44e0df7edbe3887455a0f7dcbe3017043`；旁置 `nsh/app.json`、`nsh/bundle.nshc`（9101 字节）、`nsh/capabilities.json`（全部为 false/空数组）。`Get-AuthenticodeSignature` 状态为 `NotSigned`。**这是未签名实验构建，不是发布包。**

启动该 exe 后窗口类 `NshWindow`、标题 `keex 合成实验`；宽屏侧栏顺序为 密码、验证、证件、银行、设置。以真实鼠标点击与键盘输入操作：

| 步骤 | 实际观察 | 截图 |
| --- | --- | --- |
| 启动（锁定态） | 状态“合成样本待解锁” | 01 |
| 输入公开合成口令 | masked 显示 24 个圆点；UIA 不暴露该输入框的值 | 02 |
| 解锁 | “摘要已加载”，两行摘要，口令框已清空 | 03 |
| 下一页 / 上一页 | `计时 baseline offset=2 core_ms=0.013 bridge_ms=0` | 04 |
| 搜索 `登录 Login` | 命中单行“登录 Login”（输入框内 CJK 显示方框，见 §6） | 05、05b |
| 读单字段 | 字段框显示 `synthetic-user`，“单字段已读取” | 06 |
| 改单字段 | 改为 `synthetic-nsh-edit`，“单字段已修改” | 07 |
| 另存新副本 | 再次输入口令后“已保存新副本” | 08 |
| 锁库并验证旧句柄 | “旧句柄已拒绝”，摘要与字段清空 | 09 |
| 1k：解锁/翻页/搜索/读/改/存 | 见 §9；“已保存新副本” | 10–13 |
| 10k：解锁/翻页/搜索/读/改/存 | 见 §9；“已保存新副本” | 14–17 |
| 验证切库旧句柄 | “切库旧句柄已拒绝” | 18 |

开发宿主：`nsh run "$PWD/tests/nsh_candidate" -v`（同一环境）首次构建 3m34s，进程 `nsh-app-keex-nsh-slice-windows-host.exe`（debug），日志 `Windows (DEVINBOX) connected, build 1`，并有 `application`、`statusBar` 未授权告警（预期）。经 UI Automation 驱动：解锁后出现摘要，读取后字段框为 `synthetic`、“单字段已读取”，`计时 baseline offset=0 core_ms=0.027 bridge_ms=0`，“锁库并验证旧句柄”得到“旧句柄已拒绝”（截图 34）。开发宿主未重复改单字段与另存。

运行中观察到、留给 K092 的事项：

- 打包后的 exe 把副本写回**构建机仓库路径** `tests/nsh_candidate/rust/target/outputs`（Rust 扩展里编译期的 `CARGO_MANIFEST_DIR`），样本为 `include_bytes`。该包不可搬迁，只是实验产物。
- Rust 扩展的文件写入不受 `nsh.json` 的空 capabilities 约束（它只管 JS 侧模块），与 K091 既有结论一致。
- `capabilities.clipboard=false` 时，Input 的原生 Ctrl+V 粘贴仍可用（能力只管 JS 剪贴板模块，不管原生编辑控件）。敏感字段策略需单独处理。
- 锁库后搜索框里的查询文本未被清空。
- Input 启用了系统拼写检查，`nsh` 等词下出现红色波浪线。
- 基础样本首屏顺序在不同次解锁间不同（K091 已记录的 HashMap 顺序）；1k/10k 列表区域固定高度，第 5 行被裁切。

## 6. 中文显示、输入法、键盘、可访问性

中文显示：所有 Text 标签、按钮文字、列表行（含“登录 Login”“合成集中关联账户”）显示正确。系统已有 `msyh.ttc`、`simsun.ttc`。

Input 内 CJK 显示缺陷（如实记录，未修复）：

| 输入方式 | 当前键盘布局 | 结果 | 截图 |
| --- | --- | --- | --- |
| 合成 Unicode 按键注入 | 仅 en-US | **方框**；应用收到的文本正确（搜索能命中） | 05、05b |
| 合成 Unicode 按键注入 | 微软拼音激活 | 正确 | 21 |
| 合成 Unicode 按键注入 | 切回 ENG | **方框** | 21 |
| 微软拼音 IME 组字上屏 | 微软拼音 | 正确 | 19、20 |
| Ctrl+V 粘贴 | ENG | 正确 | 22 |
| UIA `ValuePattern.SetValue` | ENG | 正确 | 23 |

因此缺陷限于“非 CJK 布局下经合成 Unicode 按键进入的 CJK 字符”。NSH 的 Win32 Input 是无窗口 RichEdit（`crates/nsh-platform-windows/src/richedit.rs`、`text_input.rs`）；字体绑定随输入时布局变化是**推断，未在上游验证或修复**。真实用户用物理键盘加 IME 的路径正常，但屏幕键盘、远程输入、自动化输入可能走到缺陷路径。

IME：加入微软拼音后以 Win+Space 切换，用真实按键输入 `denglu`，行内出现组字串 `deng'lu`，候选窗贴在输入框下方（截图 19）；空格上屏“登录”，显示正确；随后 Tab、Enter 触发搜索并命中“登录 Login”（截图 20）。只验证了微软拼音简体；未验证五笔、繁体、日韩 IME 或第三方输入法。

键盘：`windows/uia_tab_order.ps1` 记录的 Tab 顺序为 `tab-0..4 → sample-baseline → sample-1000 → sample-10000 → sample-stale → vault-password → unlock → cancel-unlock → search → search-submit → next-page → previous-page → read → field → edit → save → stale → lock` 后回绕，全部 `IsKeyboardFocusable=True`。不碰鼠标走完 选样本 → 输口令 → Space 解锁 → 搜索 → 读 → 改 → 存 → 锁库旧句柄拒绝（截图 24–27），并写出一份新副本。缺口：**聚焦的按钮没有任何可见焦点指示**（应用未定义焦点样式），用户看不出焦点在哪。

可访问性（UI Automation，`windows/uia_edits.ps1`）：

```text
window class=NshWindow framework=nsh
count ControlType.Text=6
count ControlType.Button=19
count ControlType.Edit=3
count ControlType.Pane=1
edit id=vault-password name='' help='' isPassword=True enabled=True patterns=ValuePatternIdentifiers.Pattern
edit id=search name='' help='' isPassword=False enabled=True patterns=ValuePatternIdentifiers.Pattern
edit id=field name='' help='' isPassword=False enabled=True patterns=ValuePatternIdentifiers.Pattern
button unlock patterns=InvokePatternIdentifiers.Pattern
```

通过：按钮有中文名称、AutomationId（来自 testID）与 Invoke；输入框有 Value 模式；口令框 `IsPassword=True` 且不经 UIA 泄露值。缺口：**三个输入框 Name 与 HelpText 均为空**，placeholder 没有作为可访问名称暴露，读屏用户无法知道每个框的用途；状态文本变化是否会被读屏播报未验证。

讲述人：`narrator.exe` 能启动，焦点框随 Tab 落在 keex 的按钮和口令框上（截图 28、29）。**朗读内容 BLOCKED**：虚拟机没有声音设备，`Language.TextToSpeech~~~zh-CN` 未安装。解除条件：有音频输出并装有中文语音的 Windows 真机或桌面版虚拟机，由人实际听读并记录。

## 7. `NSH_APP_DIR` 覆盖入口（K090 登记的风险）

**结论：在本次构建的 stock release runner 中仍然生效。** 源码位置 `crates/nsh-windows-app/src/lib.rs` 的 `setup()` 无条件读取该环境变量，替换 exe 旁的 `nsh/` 资源目录，随后用 `Bundle::read_trusted` 加载。

实际验证（仓库外另建一个只显示标记文字并调用 `Clipboard.readText()` 的 TSX，`nsh build --release` 得到 `bundle.nshc`；系统剪贴板预置 26 个字符的合成文本）：

| 运行方式 | 窗口标题 | 界面 | 剪贴板读取 | 截图 |
| --- | --- | --- | --- | --- |
| 不设环境变量 | keex 合成实验 | keex 合成界面 | — | 33 |
| `NSH_APP_DIR` 指向标记 bundle，其 `nsh.json` **省略** capabilities | nsh | 标记文字，keex 界面不出现 | **放行**，`length=26` | 31 |
| `NSH_APP_DIR` 指向标记 bundle，其 `nsh.json` 写 `"capabilities": {}` | nsh | 标记文字 | 被拒 `ERR_ACCESS_DENIED` | 32 |

也就是说，同一个未改动的 keex exe 只凭一个环境变量就执行了外部未签名字节码，并且**授权也跟着外部目录走**：外部目录没有 `capabilities.json` 时等于全部放开，keex 自己写的空 capabilities 不再起作用。能设置该进程环境变量的本机攻击者即可利用。本切片没有移除或拒绝此入口（需要自有受控宿主，属 K092）；不得据此宣称 Windows 包只执行固定 UI 代码。本验证只用剪贴板读取这一项能力作探针，没有尝试文件、网络或进程能力。

## 8. Win32 副本的 oracle 对照

Win32 release runner 写出的副本（`create_new`，未覆盖输入样本）：

| 样本 | 副本 | 字节 | SHA-256 | 来源 |
| --- | --- | ---: | --- | --- |
| baseline | `copy-1-1795313349872223600.kdbx` | 37,955 | `8b46a90854f5d43c3705a9db6804a6f61e4383b8ba56b7055f5afa1b33b113b5` | 鼠标键盘流程 |
| baseline | `copy-1-1795313752890622500.kdbx` | 38,019 | `e7a8937fdfbc485f0aa0bc6f647395890d16b22128b874cf01af34648b2137f7` | 纯键盘流程 |
| scale-1000 | `copy-1-1795313422598934100.kdbx` | 370,531 | `b0ec145e471287603ab485aa1c5d1953917a9e02ef4868f54318358a401b3c26` | 鼠标键盘流程 |
| scale-10000 | `copy-1-1795313463961719000.kdbx` | 3,600,995 | `96d3dd052bb3445f1080114f3df308a0812284500afa3d262bb6cf39fe0d33e1` | 鼠标键盘流程 |

`python -B tests/nsh_candidate/oracle_check.py` 读取各 `receipt-<sample>.json` 指向的副本，按原 manifest 的哈希与公开口令核对“只改了指定条目的 UserName，其余语义不变”：

```text
# receipt 指向第 1 行 baseline 副本（当时 1k/10k 仍为 headless 副本）
Ran 5 tests in 13.1s   OK
# 三份 receipt 全部指向 Win32 副本（第 1、3、4 行）
Ran 5 tests in 12.718s OK
# baseline 换成纯键盘流程副本（第 2、3、4 行）
Ran 5 tests in 12.749s
OK
```

oracle 是仓库内独立 Python 读取器的对照，不是独立人工安全复核，也不是与 KeePassXC 等第三方客户端的互通测试。副本为公开合成数据派生物，按仓库既有做法不入库。

## 9. 1k/10k 耗时观测（不是性能门槛结论）

机器见 §2（8 vCPU 虚拟机，无实体 GPU）。单次或三次观测，未做统计，未控制后台负载。

Rust 单测 `synthetic_scale_measurements`（直接调用核心，不经 UI）：

| 构建 | 条目 | unlock_ms | page50_ms | search_miss_ms |
| --- | ---: | ---: | ---: | ---: |
| debug | 1,000 | 1762.237 | 0.131 | 0.634 |
| debug | 10,000 | 6798.225 | 0.151 | 7.625 |
| release | 1,000 | 95.606 | 0.025 | 0.142 |
| release | 10,000 | 566.714 | 0.036 | 2.057 |

Win32 release runner 界面内显示的分页计时（`core_ms` 为 Rust `Instant`；`bridge_ms` 为 JS `Date.now()` 往返，毫秒分辨率，绝大多数显示 0，只能读作“分辨率不足”，不是测量值）：

| 样本 | offset=0 core_ms | offset=50 core_ms | 命中搜索 core_ms |
| --- | ---: | ---: | ---: |
| scale-1000 | 0.032 | 0.094 | 0.498 |
| scale-10000 | 0.038 | 0.098 | 2.582 |

Win32 release runner 从触发“解锁”到计时文本可见的墙钟时间（`windows/uia_unlock_timing.ps1`，经 UIA Invoke 触发并每 20 ms 轮询，**含 UIA 调用与轮询开销**，三轮）：

| 样本 | 第 1 轮 ms | 第 2 轮 ms | 第 3 轮 ms |
| --- | ---: | ---: | ---: |
| baseline | 142 | 135 | 110 |
| scale-1000 | 175 | 188 | 202 |
| scale-10000 | 633 | 700 | 664 |

headless `nsh test`（debug，经桥接）：1k offset=0 `core_ms=0.246`、`render_visible_ms=113`；10k offset=0 `core_ms=0.212`、`render_visible_ms=123`。

没有测量帧率、滚动流畅度、内存峰值、冷启动时间，也没有 debug 宿主的解锁墙钟时间。

## 10. 秘密扫描与提交

原生 Windows 不支持 hook（§4）。在 WSL Ubuntu 中对同一仓库目录执行 `python3 -S -B tests/secret_scan/scan.py`（index）与 `--worktree`，并以 `hooks.py install` 安装 pre-commit；提交从 WSL 的 git 发起，使 hook 实际运行，没有使用 `--no-verify`。必须带 `-S`：否则 Ubuntu 系统自带的 `chardet` 会被判为依赖来源不符。

截图未入库：`tests/secret_scan/policy.json` 的二进制白名单只有设计素材与合成样本两类，本切片不为截图扩大白名单。截图嵌在 PR 描述中并随汇报附上，文件名与 SHA-256 登记在 §12。

## 11. 未做与 BLOCKED

| 项 | 状态 | 解除条件 |
| --- | --- | --- |
| 代码签名（Authenticode） | BLOCKED | 提供代码签名证书（或受控签名服务）及授权；签名后重新核对 `Get-AuthenticodeSignature` 与 SmartScreen 行为 |
| 安装包（Inno Setup/MSIX） | BLOCKED | 授权安装 Inno Setup 6 或指定打包方式；并先解决 exe 输出路径不可搬迁的问题 |
| 讲述人朗读内容 | BLOCKED | 带音频输出与中文语音的 Windows 环境，由人实际听读 |
| Windows 真机、Windows 10/11 桌面版 | 未做 | 提供真机或桌面版镜像；本次只有 Server 2022 虚拟机 |
| 高 DPI、多显示器、触摸/屏幕键盘、深色模式、缩到窄屏布局 | 未做 | 需相应硬件或显示配置 |
| 实体 GPU 渲染路径 | 未做 | 本机为虚拟显示驱动 |
| 其他 IME（五笔、繁体、日韩、第三方） | 未做 | 安装相应输入法后逐一检查 |
| `NSH_APP_DIR` 入口移除/拒绝、固定资源签名校验 | 未实现 | K092 自有受控宿主 |
| Input 内 CJK 方框缺陷修复 | 未修 | 需在上游 NSH 或自有宿主定位；不在 `tests/nsh_candidate/` 可改范围内 |
| 输入框可访问名称、可见焦点样式 | 未修 | 属界面实现工作，本切片只记录缺口 |
| 独立安全复核 | 未做 | 需独立审查者 |
| 开发宿主内的改/存流程、剪贴板以外能力的越权探测 | 未做 | 可在后续切片补 |

## 12. 截图清单

除 05b 与部分规模计时图为局部放大外，均为整屏未裁剪；画面只含公开合成数据，口令框为圆点遮罩。

| 文件 | SHA-256 |
| --- | --- |
| `01-launch-locked.png` | `81f078c9bb6268201474e80985718a4ad5c6205aaa79d1c9671bec3c0de1dc49` |
| `02-password-masked.png` | `f55133b65bc1cfd72fbd8804e67a8b2778ae75acab26d82243cd9c5714035d04` |
| `03-unlocked-page0.png` | `5b8b9dd6ed0cfd8bf366098c586f66eb46962abab6852e625bf1eee9a22b1eb6` |
| `04-next-page.png` | `91b78dd39306aeaa576e3b5801f0f3270003aab750d8321e1bfacf916edece36` |
| `05-search-chinese-input-tofu.png` | `80cd7c17eaa0507ab7fe97805a3e5659ed45f4a6ce4bc9ebcd844919fead3e0f` |
| `05b-zoom-input-tofu.png` | `ba240dbd63149760304c70c19b0e77cf7269af66fc61fe9b898b5f49325e3610` |
| `06-read-field.png` | `0dfa52369bc3a5e3a6af5de98d2e61016b2eb0df08999fdf1413fe362b2f1a98` |
| `07-edit-field.png` | `05b261f51027ce34fb409200f2417e1c57ad86ff9f5e44d93f8cdfea20211da4` |
| `08-saved-copy.png` | `d5664ca2f70b89cf40280a270641704d6df656fee03d14fe66cc5103a74d5b53` |
| `09-lock-stale-rejected.png` | `06353a85ee90aae8c11d11b19259339c214ffee839aaa2ddcd7ae933c0a8ee32` |
| `10-scale1000-unlocked.png` | `c96af26524202fa0e72eab86a0c1b479d80c6442aa6bc35a21486447157fc53c` |
| `11-scale1000-page-offset50.png` | `aa218a8af1ae60aa09b448e6e80d81c1123cd65a4358ff38391b575b14fa0acc` |
| `12-scale1000-search.png` | `ac7ff33df4d33fae49e22bbaa72b69b4762b3f88742524ccdb26404ac34c381b` |
| `13-scale1000-saved.png` | `8b50427a3f70a177197aa555582a6be67ec3290e186f0e2a757e2d90d2319bdf` |
| `14-scale10000-unlocked.png` | `785dd1fc9e551d2cb604e45c23482222907fcd5cf089253fca464b68091f6dc9` |
| `15-scale10000-page-offset50.png` | `fc8c08d0716594839c6848dee3b3c0784962a7586d6e8acadf9216697c1a1f52` |
| `16-scale10000-search.png` | `c6fc7b0bfdc27dbec4453d99d042391efae89dd25a46b9cc3d0c92281f6bb935` |
| `17-scale10000-saved.png` | `4caf60f8f17ec607a774715eb0d778b46c9801f09816768d33f6178d576ea0f1` |
| `18-switch-stale-rejected.png` | `14fdaa208405449b52e5ad0d1756ab1c005ea192ad4e973a71cc3e2d020ea8d6` |
| `19-ime-pinyin-candidates.png` | `c18f0bbc3c112b427db3de653fb36c45d17411d6245b59641ed9b31d18b4db55` |
| `20-ime-committed-tab-enter-search.png` | `e06d53468d7d7542b4b2e9ca92d47d59a980531d5b4a1714fdd26c077b11465c` |
| `21-layout-dependent-tofu.png` | `16c1f8b32d606b30068b1dae36bdccdf260ff66d8159106d750a171cfa70e9fa` |
| `22-paste-chinese-eng-layout.png` | `0e67ed358ee53bc24d5d9180a059ffad8e52e9599ed9e0f63751df2ca7f7eb27` |
| `23-uia-setvalue-chinese.png` | `ee9812254e6b44c397f3e1d6d42d87cc21d600388bd8a1c4d5aca00e01a970d7` |
| `24-keyboard-only-unlock.png` | `7cc4a670147dfe996631c8e1c8cb86d9cb0911577dd7069cafa38d705a9f9789` |
| `25-keyboard-only-edit.png` | `0c9efc2336cdc75697e1f5ef482c6c79e2a67cda87ddf936a206fdcb82977734` |
| `26-keyboard-only-save.png` | `43459d237e2059bbfba91a3660a63b0a6fa10a1a7e98ea746b47dde5fae707ba` |
| `27-keyboard-only-lock-stale.png` | `b1f496d229b7f29ef2221c5f62d2563554b5f3ab095af87f95c856de7d2f621e` |
| `28-narrator-focus-button.png` | `8771df67ce0099170a3337ee35ffc53dd17c9e1f865652c3ead76f70a099e0a4` |
| `29-narrator-focus-password.png` | `51af65faf207c3aa7b7bcb40dcfff2b46fe08f4581adc6b48f675e2ca33ea7b1` |
| `31-appdir-override-marker-open.png` | `c0562870e4afd95805728ab5cb3635005b548ad4668056f10fc3048d43e7aaed` |
| `32-appdir-override-marker-denied.png` | `2861c6e0ae89d91621900fb400554edc728d1c5b0c60f6ca0ed63d83df646c52` |
| `33-appdir-control-no-env.png` | `7698c97ca320a8910cd4c2df6366d8490b2897d9d68bf9c0177401e4426aad51` |
| `34-dev-host-nsh-run-read.png` | `0702c06d08974f42fe8636af72867ed423ce122ca80174d912d8c118206ab0bb` |
