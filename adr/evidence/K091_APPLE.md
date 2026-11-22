# K091：macOS AppKit 与 iOS 模拟器平台切片

日期：2026-11-21（本机时钟）。**K091 仍为 DOING。本文件只记录 macOS 桌面（ad hoc 签名包）与 iOS 模拟器两处实际运行结果；不代表 iOS 真机、iPad、Android、Windows、Web 任一端通过，不是发布包、独立安全复核或性能门槛结论。** 只使用仓库公开 L0 合成样本与合成口令。Linux-headless 切片见 [K091](K091.md)，固定输入见 [K090](K090.md)，复现入口见 [nsh_candidate README](../../tests/nsh_candidate/README.md) 的 Apple 小节。

基线分支 `devin/1795273556-k091-nsh-rust-slice`（`2f27fc9`），工作分支 `devin/1795311320-k091-apple-slice`。

## 1. 环境

| 项 | 实际值 |
| --- | --- |
| 机型 | `VirtualMac2,1`，Apple M4 Pro (Virtual)，12 核，16 GiB（云端虚拟机，不是实体 Mac） |
| 系统 | macOS 26.6.2（25G83），Darwin 25.6.0 |
| Xcode | 26.6（17F113）；模拟器运行时 iOS 26.5（23F73）、iOS 27.0（24A434） |
| 模拟器 | iPhone 17，iOS 26.5，UDID `EDD9B083-63F1-44E6-9A7B-0A6964CC2561` |
| NSH | `https://github.com/longbridge/nsh` tag `v0.6.1`，提交 `2f51d8611677c8a6bbad937b39756e8d0cc45350`，独立 checkout `$HOME/nsh-k090`，工作树干净；`nsh --version` 输出 `nsh 0.6.1 (2f51d86)` |
| Rust | 见下方“工具链偏差”：日志 01–14 为 rustc/cargo 1.99.0，日志 16 起为 1.100.0（`0ef1bc386 2026-11-09`），均为 `stable-aarch64-apple-darwin` |
| Python | 3.12.15（`python3.12`；系统自带 3.9 不满足 `scripts/check.py`） |
| 签名 | `security find-identity -v -p codesigning` → `0 valid identities found` |

**工具链偏差（本会话造成，如实记录）**：在 `$HOME/nsh-k090` 内执行了一条未带 `RUSTUP_TOOLCHAIN` 的 `rustup target list --installed`，rustup 按上游 `rust-toolchain.toml`（滚动 `stable` + 6 个目标）把全局 stable 从 1.99.0 同步到 1.100.0，并装上 `aarch64-apple-ios`、`aarch64-apple-ios-sim`、`aarch64-apple-ios-macabi` 与 3 个 Android 目标。均为免费 rustup 组件，不涉及账号或付费，但属于未经确认的全局变更；未回滚。此后命令都显式 `RUSTUP_TOOLCHAIN=stable-aarch64-apple-darwin`。因此 macOS 首轮结果是 1.99.0，改动后的回归与全部 iOS 结果是 1.100.0，两者不混写。

用户级/项目级安装（无 sudo、无付费）：`detect-secrets` 等秘密扫描依赖、`tests/kdbx_oracle/.deps-argon2` 内的 `argon2-cffi 25.1.0`/`argon2-cffi-bindings 26.1.0`（已忽略目录）。没有安装 Xcode 组件、证书或描述文件。

## 2. 固定 CLI 与 Linux 已通过检查在 macOS 的复跑

公共环境：

```sh
export PATH=/opt/homebrew/opt/rustup/bin:$PATH
export RUSTUP_TOOLCHAIN=stable-aarch64-apple-darwin
NSH="$HOME/nsh-k090/target/debug/nsh"
```

| # | 命令（均在 xeek 根，除 CLI 构建外） | 结果 | 日志尾部 |
| --- | --- | --- | --- |
| 01 | `cargo build --locked -p nsh-cli`（在 `$HOME/nsh-k090`） | rc=0 | `Finished dev profile [unoptimized + debuginfo] target(s) in 1m 46s` |
| 05 | `cargo test --locked --manifest-path tests/nsh_candidate/rust/Cargo.toml --lib -- --nocapture --test-threads=1`（1.99.0） | rc=0 | `test result: ok. 5 passed; 0 failed; 0 ignored` |
| 16 | 同上（1.100.0） | rc=0 | `test result: ok. 5 passed; 0 failed; 0 ignored` |
| 06 | `CARGO_TARGET_DIR="$HOME/nsh-k090/target" "$NSH" test "$PWD/tests/nsh_candidate" --trace` | rc=0 | `✓ 11 tests: 11 passed, 0 failed (1m 55s)` |
| 07 | `python3.12 -B tests/nsh_candidate/oracle_check.py -v` | rc=0 | `Ran 5 tests in 8.816s` / `OK` |
| 08 | `python3.12 -B scripts/check.py` | rc=0 | `Ran 63 tests in 0.031s` / `OK` / `4 组基线检查通过；不代表生产或平台能力验收。` |
| 24 | 06 在代码改动后重跑（1.100.0） | rc=0 | `✓ 11 tests: 11 passed, 0 failed (2m 13s)` |
| 32 | 08 在全部改动后重跑 | rc=0 | 同 08 |

目录级 11 项仍是 5 项 Rust 测试加 6 项 TSX 测试。`patched_source()` 准备步骤（README 既有命令）在 macOS 上 rc=0，输出 `tests/wasm_core/target/source/keepass-0.15.3`。oracle 首次运行缺 `argon2`，装入项目缓存后通过；依赖安装不算检查项。

## 3. macOS 桌面（AppKit 宿主）

### 3.1 `nsh test --target macos`

```sh
CARGO_TARGET_DIR="$HOME/nsh-k090/target" "$NSH" test "$PWD/tests/nsh_candidate" --target macos
python3.12 -B tests/nsh_candidate/oracle_check.py -v
```

| # | 结果 | 尾部 |
| --- | --- | --- |
| 09（1.99.0） | rc=0 | `✓ built the development host for macOS (54.8s, 1 warning)` … `✓ 6 tests: 6 passed, 0 failed (1m 31s)` |
| 10 | rc=0 | `Ran 5 tests in 9.517s` / `OK` |
| 25（改动后，1.100.0） | rc=0 | `✓ 6 tests: 6 passed, 0 failed (1m 47s)` |
| 26 | rc=0 | `OK` |

`--target` 模式不重复跑 Rust 单测（CLI 输出 `the crates' Rust tests (cargo test) run without --target`），所以是 6 项。每个用例都打印 `warn the application … is not granted` 与 `warn the status bar is not granted`；`Denied.test.tsx` 在原生宿主上仍以两次 `ERR_ACCESS_DENIED` 通过。未为消除告警改动 `nsh.json`，`capabilities` 仍为显式 `{}`。

### 3.2 打包并人工走流程

```sh
"$NSH" package "$PWD/tests/nsh_candidate" --target macos --out "$HOME/k091-apple-out/macos"
open "$HOME/k091-apple-out/macos/keex 合成实验.app"
```

日志 11 / 28（改动后重打）：`✓ built the release runner for macOS` / `✓ packaged …/keex 合成实验.app`，rc=0，包 44 MB。`codesign -dv`：`Identifier=dev.keex.nshcandidate`、`Signature=adhoc`、`TeamIdentifier=not set`。**这是 ad hoc 签名的 release runner，不是 Developer ID 签名、公证或发布包。**

人工流程通过鼠标/键盘事件与辅助功能动作驱动真实窗口，共两轮：首轮在改动前的包上（截图 01–17），第二轮在改动后重打的包上（截图 22–27）。

| 步骤 | 实际结果 | 截图 |
| --- | --- | --- |
| 启动 | 窗口标题 `keex 合成实验`，宽屏侧栏顺序 密码/验证/证件/银行/设置，状态 `合成样本待解锁` | `macos-01-launch` |
| 口令输入 | 输入框显示圆点，不回显明文 | `macos-02-password-masked` |
| 解锁 | `摘要已加载`，基础样本每页 2 条 | `macos-03-unlocked-keyboard` |
| 分页 | `下一页` 后 offset 前进，条目更换 | `macos-04-next-page-keyboard` |
| 搜索 | 拼音输入 `denglu` 选“登录”，命中 `登录 Login` | `macos-05-ime-candidates`、`macos-06-ime-search-result` |
| 读单字段 | 编辑框出现 `synthetic-user`，状态 `单字段已读取` | `macos-07-read-field` |
| 改单字段 | 改为 `synthetic-nsh-edit`，状态 `单字段已修改` | `macos-08-edit-field` |
| 另存新副本 | 重新输入合成口令后 `已保存新副本` | `macos-10-saved-copy` |
| 锁库后旧句柄 | 列表、字段、计时清空，状态 `旧句柄已拒绝` | `macos-11-locked-stale-rejected` |
| 1k | 第二页 50 条区间、保存成功 | `macos-12-scale1000-page2`、`macos-13-scale1000-saved` |
| 切库旧句柄 | 切换样本后 `切库旧句柄已拒绝` | `macos-14-switch-stale-rejected` |
| 10k | 第二页、保存、锁库后 `旧句柄已拒绝` | `macos-15`、`macos-16`、`macos-17` |
| 改动后的包（回归） | 拼音搜索、Tab+空格触发搜索、读/改/保存（基础、1k、10k）、锁库拒绝 | `macos-22` … `macos-27` |

### 3.3 中文显示、输入法、键盘、可访问性

- **中文显示**：标题、导航、按钮、占位符、状态、合成条目标题均正常显示，没有豆腐块或乱码。摘要区是固定高度滚动区，第 5 行被裁切一半（1k/10k 截图可见），属于实验页布局，不是字体问题。未检查深色模式、窗口缩放与窄宽度。
- **中文输入法**：系统“简体拼音”（`com.apple.inputmethod.SCIM.ITABC`）。在搜索框输入 `denglu`，出现内联组字 `deng lu` 与候选条（登录/登录号/登陆…），空格上屏“登录”，搜索命中。焦点进入口令框（masked）时系统输入源自动回到 ABC，拼音不参与（`macos-09-masked-field-ime-suppressed`）。只验证了系统拼音，没有验证第三方输入法、五笔或手写。
- **键盘**：Tab 在控件间移动焦点，空格触发聚焦的按钮（解锁、下一页、搜索摘要均以此触发过）；`⌘A` 全选输入框内容后可直接覆盖。未逐一验证 Shift+Tab 逆序、Return 触发、焦点环可见性与完整 Tab 顺序。
- **辅助功能树**（AXUIElement 读取）：14 个操作控件全部是 `button`，名称为中文可见文本并带 `testID` 标识（如 `button "打开并解锁合成样本" #unlock`）；三个输入框是 `textfield`，名称取占位符（口令框在这棵树里也只是 `textfield`）；五个导航是 `button "密码"…"设置"`；状态与计时是 `statictext`。通过辅助功能 `press` 动作可以触发按钮。导航没有暴露“已选中”状态，状态文本变化没有作为通知播报，这两点未达可用性结论。
- **VoiceOver**：实际打开过 VoiceOver，字幕面板读出 `打开并解锁合成样本, button`（`macos-21`），口令框读为安全文本框并提示内容不显示、不朗读（`macos-20`）。用 AppleScript 取完整朗读文本失败：`Not authorized to send Apple events to VoiceOver. (-1743)`。**所以只有三张字幕截图，没有完成整页 VoiceOver 走查，也没有人工听读确认。** Accessibility Inspector 未使用。

### 3.4 `NSH_APP_DIR` 覆盖入口（K090 风险）

固定提交 `crates/nsh-macos-app/src/lib.rs` 在 release runner 中仍读取 `NSH_APP_DIR`，存在时用它替代 `Contents/Resources/nsh`。实测：

```sh
# 探针资源来自另一个临时应用的打包产物（仓库外，未入库）：
# app.json 名称改为“NSH_APP_DIR 覆盖窗口”，capabilities.json 仅 clipboard=true，bundle 为探针页面。
NSH_APP_DIR="$HOME/k091-apple-out/probe-resources" \
  "$HOME/k091-apple-out/macos/keex 合成实验.app/Contents/MacOS/keex"
```

结果（`macos-18-nsh-app-dir-override`）：**覆盖仍然生效。** 同一个 keex 包的可执行文件加载了外部目录的界面与能力声明，窗口标题变为 `NSH_APP_DIR 覆盖窗口`，页面显示 `NSH_APP_DIR 覆盖探针 · 非包内资源`；点击探针按钮后显示 `剪贴板写入放行`，`pbpaste` 得到 `k091-nsh-app-dir-probe`，而包内 `capabilities` 是 `{}`。也就是说，能设置该进程环境变量的一方可以替换 UI 代码并扩大能力，包的 ad hoc 签名不覆盖这个目录。本切片没有修改 NSH 宿主去关闭它；这是进入生产骨架前必须处理的缺口（固定 release host 需去除或签名校验该入口），K090 的风险记录继续成立。未测试 Hardened Runtime、公证或 Developer ID 签名是否改变此行为（没有签名资源）。

## 4. iOS 模拟器

### 4.1 `nsh test --target ios`

```sh
CARGO_TARGET_DIR="$HOME/nsh-k090/target" "$NSH" test "$PWD/tests/nsh_candidate" --target ios
python3.12 -B tests/nsh_candidate/oracle_check.py -v
```

| # | 结果 | 说明 |
| --- | --- | --- |
| 17 | rc=1 | 编译中 `rustc-LLVM ERROR: IO failure on output stream: No space left on device`；清理仓库外 NSH `target` 内的中间产物后重试，不是代码问题 |
| 18 | rc=1，`6 tests: 4 passed, 2 failed` | `open("./App.tsx"): width is unsupported on --target ios: the app fills the device's screen` |
| 19 | rc=1，`4 passed, 2 failed` | 去掉视口后，两条用例停在“单字段已修改”：iOS 把输入的 `synthetic-nsh-edit` 自动改成 `Synthetic-msg-edit` |
| 21 | rc=1 | 对上一轮（被自动纠正的）副本跑 oracle：`ValueError: edit missing`，oracle 没有放行错误编辑 |
| 22 | rc=0 | `✓ built the development host for the iOS simulator` … `✓ 6 tests: 6 passed, 0 failed (1m 38s)` |
| 23 | rc=0 | 对 22 生成的三份副本：`Ran 5 tests in 11.375s` / `OK` |

两处失败对应的最小改动（仅 `tests/nsh_candidate/`）：

1. `Vault.test.tsx`、`Scale.test.tsx`：`open` 带固定视口失败且错误码为 `ERR_NSH_TEST_UNSUPPORTED` 时，退回不带尺寸的 `open`；其他错误照常抛出。headless/macOS 仍用 1024×1600。
2. `VaultPanel.tsx`：搜索框与字段编辑框加 `autoCapitalize="none"`、`autoCorrect={false}`。NSH 文档说明 iOS 默认 `sentences` 与自动纠正；条目字段被系统静默改写属于数据正确性问题，不是测试适配。口令框是 masked，未改。

没有修改 Rust、`nsh.json`、capabilities、fixture、oracle 或 writer。

### 4.2 打包到模拟器并人工走流程

```sh
"$NSH" package "$PWD/tests/nsh_candidate" --target ios-simulator --out "$HOME/k091-apple-out/ios-sim" --run
```

日志 27：`✓ built the release runner for the iOS simulator` / `✓ packaged …/keex 合成实验.app` / `✓ launched dev.keex.nshcandidate in the simulator`，rc=0，包 44 MB，`Signature=adhoc`、`TeamIdentifier=not set`。

人工流程在改动后的包上完成（Simulator 窗口内点击、Mac 键盘输入、辅助功能动作），截图由 `xcrun simctl io booted screenshot` 取得：

| 步骤 | 实际结果 | 截图 |
| --- | --- | --- |
| 启动 | 底部导航 密码/验证/证件/银行/设置，状态 `合成样本待解锁` | `ios-01-launch` |
| 口令输入 | 圆点遮蔽 | `ios-02-password-masked` |
| 解锁 | `摘要已加载`，`计时 baseline offset=0 core_ms=0.003 bridge_ms=0` | `ios-03-unlocked` |
| 分页 | `下一页` 后条目更换 | `ios-04-next-page` |
| 搜索（英文小写） | 输入 `login` 得到 `无匹配摘要`；条目标题是 `登录 Login`，说明标题搜索区分大小写，输入也未被自动大写 | `ios-05-search-miss-case-sensitive` |
| 搜索（拼音） | 给模拟器加“简体拼音”键盘（`xcrun simctl spawn booted defaults write -g AppleKeyboards …`，只改该模拟器的偏好）后用 Mac 键盘输入 `denglu`，出现组字与候选栏，选“登录”，命中 `登录 Login` | `ios-07`、`ios-08`、`ios-09` |
| 读单字段 | `synthetic-user`，`单字段已读取` | `ios-10-read-field` |
| 改单字段 | `synthetic-nsh-edit` 原样保留，`单字段已修改` | `ios-11-edit-field` |
| 另存新副本 | `已保存新副本` | `ios-12-saved-copy` |
| 锁库后旧句柄 | 内容清空，`旧句柄已拒绝` | `ios-13-locked-stale-rejected` |
| 1k | 第二页（offset=50）、粘贴中文“合成集中关联账户”搜索命中、读/改/保存 | `ios-14`、`ios-15`、`ios-16` |
| 切库旧句柄 | `切库旧句柄已拒绝` | `ios-17-switch-stale-rejected` |
| 10k | 第二页、读/改/保存、锁库后 `旧句柄已拒绝` | `ios-18`、`ios-19`、`ios-20` |

`ios-00-before-fix-autocorrect-mangled` 是改动前的失败现场（字段显示 `Synthetic-msg-edit`），保留作为问题证据，不是通过证据。

模拟器上观察到、未在本切片修复的问题：

- **顶部安全区**：`keex` 标题与状态栏时钟重叠（所有 iOS 截图可见）。页面没有处理顶部安全区；`statusBar` 能力未授予，本切片不为此扩大能力。
- **软键盘遮挡**：软键盘弹出后遮住“读取首条用户名”以下的全部控件，页面不滚动、不避让（`ios-06`）；人工流程靠 `⌘K` 收起键盘继续。真机上没有硬件键盘时这一步会卡住，需要页面级处理。
- **“Passwords”自动填充条**：搜索框聚焦时键盘上方出现系统 `Passwords` 入口（`ios-06`）。普通搜索框不应被系统当作凭据字段，需要在后续切片确认 NSH 输入框的内容类型设置。
- **摘要区第 5 行裁切**：与 macOS 相同。
- **辅助功能**：模拟器辅助功能树共 28 个节点：14 个操作控件与 5 个导航为 `button`，名称为中文可见文本，可用辅助功能 `press` 触发；3 个输入框为 `textinput`，**没有名称，占位符只出现在值里**，输入内容后读屏将失去字段说明；状态文本是普通 `label`，变化不播报。**没有开 VoiceOver（模拟器不提供），没有用 Accessibility Inspector 审计，动态字体、深色模式、横屏、iPad 均未运行。**

### 4.3 另存副本落在哪里（重要边界）

模拟器进程与宿主共用文件系统，`rust/src/lib.rs` 里编译期的 `CARGO_MANIFEST_DIR/target/outputs` 在模拟器内就是 Mac 上的仓库路径，所以“另存新副本”直接写进了本机构建目录，oracle 也直接读到。**这只在模拟器成立。真机没有这个路径，现有写法在真机上预期无法保存。** 并行的 Android 切片已把 `output_dir()` 改为 iOS/Android 使用 NSH 私有 `data_dir()/outputs`；本切片在模拟器上没有遇到写入失败，因此没有改 Rust，合并 Android 切片后需在模拟器重跑本节，并在真机验证（见 BLOCKED）。

## 5. 另存副本的 oracle 对照

每次都先清空 `tests/nsh_candidate/rust/target/outputs`，再由对应宿主生成 `copy-*.kdbx` 与三份 receipt，然后运行未改动的 `oracle_check.py`（按 manifest SHA 核对源样本；除目标条目 UserName、新增历史快照、`LastModificationTime` 外任何语义差异都失败；含无编辑/无关修改/目标缺失三个负控制）。

| # | 副本来源 | 结果 | 副本 SHA-256（前 12 位：基础 / 1k / 10k） |
| --- | --- | --- | --- |
| 07 | headless `nsh test` | 5/5 OK | 未留存 |
| 10、26 | macOS 开发宿主 `nsh test --target macos` | 5/5 OK | 未留存 |
| 12 | macOS ad hoc 包人工流程（改动前） | 5/5 OK | `232c4b35f3ec` / `dc0d5d09776b` / `07582bc37b80` |
| 31 | macOS ad hoc 包人工流程（改动后） | 5/5 OK | `479f026359ce` / `131e39fb775a` / `f6452cc718c0` |
| 23 | iOS 模拟器开发宿主 `nsh test --target ios` | 5/5 OK | 未留存 |
| 29 | iOS 模拟器 ad hoc 包人工流程 | 5/5 OK | `aabf73f2aa27` / `c2413e77478e` / `576d8c2a14dd` |
| 21 | iOS 改动前被自动纠正的副本 | **失败**（`edit missing`，另两份 receipt 缺失） | 负面证据 |

副本大小：基础 38 723 B，1k 368 947 B，10k 3 572 403 B。副本与日志都在仓库外或已忽略目录，未入库。结论仅限：这三类宿主产出的副本在现有 oracle 规则下未修改语义不变；不等于 KeePassXC/KeePass 2 互操作复验（K091 原证据的范围不变）。

## 6. 1k/10k 计时（记录，不是门槛）

机型见 §1（云端虚拟 Mac，12 核 M4 Pro Virtual）；单次运行，无预热、无重复、无统计。

**Rust 核心直测**（`synthetic_scale_measurements`，宿主 macOS arm64，不经 UI/桥）：

| 构建 | rustc | 规模 | unlock_ms | page50_ms | search_miss_ms |
| --- | --- | --- | ---: | ---: | ---: |
| debug（`test` profile，未优化） | 1.99.0 | 1k | 959.319 | 0.089 | 0.524 |
| debug | 1.99.0 | 10k | 5154.566 | 0.149 | 9.375 |
| debug | 1.100.0 | 1k | 1165.191 | 0.096 | 0.644 |
| debug | 1.100.0 | 10k | 5281.553 | 0.130 | 8.372 |
| release（`cargo test --release`，日志 30） | 1.100.0 | 1k | 46.209 | 0.028 | 0.110 |
| release | 1.100.0 | 10k | 336.307 | 0.043 | 1.830 |

**经 TSX→Rust 桥的分页**（第二页 offset=50，50 条）：

| 宿主 | 构建 | 规模 | core_ms | bridge_ms | render_visible_ms |
| --- | --- | --- | ---: | ---: | ---: |
| headless（日志 24） | `nsh test` 开发 runner | 1k / 10k | 0.211 / 0.224 | 0 / 1 | 119 / 122 |
| macOS AppKit（日志 25） | `nsh test` 开发宿主 | 1k / 10k | 0.191 / 0.234 | 1 / 1 | 306 / 304 |
| iOS 模拟器（日志 22） | `nsh test` 开发宿主 | 1k / 10k | 0.174 / 0.212 | 2 / 1 | 356 / 376 |
| macOS AppKit 包（截图 12、15） | release runner，ad hoc | 1k / 10k | 0.063 / 0.087 | 0 / 0 | 未测 |
| iOS 模拟器包（截图 14、18） | release runner，ad hoc | 1k / 10k | 0.056 / 0.119 | 0 / 1 | 未测 |

口径与 K091 相同：`core_ms` 是 Rust `Instant` 测分页与摘要构造；`bridge_ms` 是 JS `Date.now` 的 Promise 往返，毫秒分辨率；`render_visible_ms` 含测试驱动与轮询，不是渲染耗时或帧率；三列不可相加。`nsh test` 开发宿主的 Cargo profile 没有另行确认。**应用内的解锁没有计时**（页面只显示分页计时），解锁数字只来自上面的 Rust 直测；iOS 目标上的解锁耗时没有测。模拟器运行的是 Mac CPU 上的 arm64 模拟器构建，不能代表任何 iPhone/iPad。没有测内存、帧率、冷启动、滚动或包体优化。

## 7. 做了 / 没做 / BLOCKED

**做了并通过**：固定 CLI 构建；Rust 单测、headless `nsh test`、oracle、`scripts/check.py` 在 macOS 复跑；macOS 与 iOS 模拟器的 `nsh test --target`；两端 ad hoc 包的人工完整流程（基础/1k/10k）；四组副本 oracle；macOS 拼音输入、键盘、辅助功能树；iOS 模拟器拼音输入与辅助功能树；`NSH_APP_DIR` 实测。

**做了且结果为问题**：`NSH_APP_DIR` 在 release runner 仍可替换 UI 与能力（§3.4）；iOS 顶部安全区重叠、软键盘遮挡、`Passwords` 条（§4.2）；iOS 默认自动纠正会改写字段（已在实验页关闭）；标题搜索区分大小写（核心既有行为，仅记录）。

**没做**：整页 VoiceOver 走查与人工听读、Accessibility Inspector 审计；深色模式、动态字体、窗口缩放、横屏、iPad、Mac Catalyst；第三方输入法；多窗口、后台/前台切换、进程被杀后的状态；锁屏/应用切换器快照遮蔽；宿主 capability 白名单接线（`host-grants.json` 仍未接入）；内存/帧率/冷启动；iOS 目标的解锁耗时；合并 Android 切片的 `output_dir()` 后的重跑。

**BLOCKED**：

| 项 | 原因 | 解除条件 |
| --- | --- | --- |
| iOS 真机运行同一流程 | 本机无 iPhone/iPad；无 Apple 开发者账号、开发证书与描述文件（0 个有效签名身份） | 提供测试设备、专用开发者团队的开发证书与包含 `dev.keex.nshcandidate` 的描述文件；并先合并 `output_dir()` 的私有目录写法 |
| iOS 真机 VoiceOver、硬件键盘缺失时的软键盘流程、真机计时 | 同上 | 同上 |
| macOS Developer ID 签名、Hardened Runtime、公证、Gatekeeper 首次打开 | 无 Developer ID 证书与公证凭据 | 提供 Developer ID Application 证书与公证用专用账号/密钥 |
| `NSH_APP_DIR` 在已签名加固包上的行为 | 依赖上一项 | 同上；或在固定 release host 中去除/校验该入口后重测 |
| 整页 VoiceOver 朗读记录 | 本会话无法授予对 VoiceOver 的 Apple Events 权限，也没有人工听读 | 由人在本机授予自动化权限，或人工操作并记录 |
| 独立安全复核 | 需要独立审查者，本会话不能自评 | 安排独立审查 |

## 8. 证据文件

日志在 `$HOME/k091-apple-logs`（仓库外，未入库），编号与上表一致。截图在 `$HOME/k091-apple-shots`，共 48 张（macOS 27 张、iOS 21 张），随 PR 描述与会话附件提供，不入库；全部只含公开合成数据。macOS 截图是整屏 1600×1200，iOS 截图是模拟器帧缓冲 1206×2622。
