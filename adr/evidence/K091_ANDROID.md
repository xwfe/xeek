# K091：Android 模拟器平台切片

日期：2026-11-22。**K091 仍为 DOING。本文件只记录 Android 模拟器（x86_64，API 35）上的实际运行结果；不代表 Android 真机、ARM 设备、其他系统版本或其他平台通过，不是发布包、独立安全复核或性能门槛结论。** 只使用仓库内公开合成样本。

基线：macOS / iOS 切片分支 `devin/1795311320-k091-apple-slice`（`f5ac7a6`），其上叠加本切片。

## 1. 环境

| 项 | 实际值 |
| --- | --- |
| 主机 | Ubuntu 22.04.5，Intel Xeon 8 vCPU（云端虚拟机），31 GiB，`/dev/kvm` 可用 |
| Rust | rustc / cargo 1.100.0，target `x86_64-linux-android`（另两个 ABI 也已装） |
| NSH | 固定提交 `2f51d8611677c8a6bbad937b39756e8d0cc45350` 构建的 `nsh 0.6.1` |
| Android SDK | 用户目录 `~/Android/Sdk`；cmdline-tools 19.0、platform-tools 37.0.3、build-tools 35.0.1、platforms android-35、NDK 27.2.12479018、emulator 37.3.10 |
| 系统镜像 | `system-images;android-35;google_apis;x86_64` r9，Android 15，`userdebug` |
| AVD | `keex35`，Pixel 6 配置，1080×2400 / 420 dpi，RAM 4 GiB，数据分区 12 GiB，`-no-window -gpu swiftshader_indirect` |
| JDK | OpenJDK 17（17.0.20 系列，主机已有） |
| libclang | 用户目录解包的 LLVM 14（K090 已有），经 `LIBCLANG_PATH` 提供给 bindgen；NDK r27 不再自带 libclang |

SDK 由用户授权安装，并经授权接受 Google SDK 许可（`sdkmanager --licenses`）。没有 sudo，没有改全局环境。

磁盘：`nsh test --target android` 的开发宿主会为三个 ABI 各构建一份 debug 运行时，三个 target 目录合计约 46 GiB，开发宿主 APK 3.4 GiB。第一次打包发布运行时时磁盘写满并失败，删掉另外两个 ABI 的构建目录后重跑成功。AVD 默认 6 GiB 数据分区装不下开发宿主 APK（`INSTALL_FAILED_INSUFFICIENT_STORAGE`），改为 12 GiB。

## 2. 代码改动（仅 `tests/nsh_candidate/`）

- `rust/src/lib.rs`：`output_dir()` 在 Android 上改用 NSH 的 `data_dir()`（应用私有数据目录）下的 `outputs`，其他平台仍写 `rust/target/outputs`。原来的路径是编译机上的 `CARGO_MANIFEST_DIR`，设备上不存在。目录在 `save_copy` 取走会话之前获取，失败不会丢会话。iOS 模拟器与 Mac 共用文件系统，原路径可写，已由 macOS / iOS 切片验证；iOS 真机会遇到同样的问题，等有真机时在那边改并验证，这里不动。
- `oracle_check.py`：可用环境变量 `KEEX_NSH_OUTPUTS` 指向从设备拉回的输出目录；默认行为不变。

两个测试在手机目标上退回设备屏幕尺寸的改动来自 macOS / iOS 切片，本切片直接复用。

## 3. `nsh test --target android`（开发宿主，真实触摸与按键事件）

```sh
. ~/android-env.sh   # ANDROID_HOME、PATH、CARGO_TARGET_DIR、LIBCLANG_PATH、LD_LIBRARY_PATH
"$HOME/nsh-k090/target/debug/nsh" test "$PWD/tests/nsh_candidate" --target android
```

```text
✓ tests/nsh_candidate/App.test.tsx › 五导航和合成空态 (3.3s)
✓ tests/nsh_candidate/Denied.test.tsx › 无 network/openUrl 授权必须拒绝而非网络故障 (2.4s)
K091 entries=1000 render_visible_ms=470 计时 scale-1000 offset=50 core_ms=0.496 bridge_ms=4
K091 entries=10000 render_visible_ms=373 计时 scale-10000 offset=50 core_ms=0.331 bridge_ms=3
✓ tests/nsh_candidate/Scale.test.tsx › 规模样本经 TSX Rust 桥分页搜索编辑并拒绝切库旧票据 (35.2s)
✓ tests/nsh_candidate/Vault.test.tsx › 合成 Rust 核心纵向流程 (11.6s)
✓ tests/nsh_candidate/Vault.test.tsx › 错误密码不产生会话 (4.2s)
✓ tests/nsh_candidate/Vault.test.tsx › 尚未调度的解锁也必须能取消 (3.8s)
✓ 6 tests: 6 passed, 0 failed (1m 3s)
```

改动前同一命令是 4 通过、2 失败：两个测试指定了窗口尺寸，手机目标拒绝（`width is unsupported on --target android`）。

三份另存副本从开发宿主的私有目录拉回后交给 oracle：

```sh
KEEX_NSH_OUTPUTS=<拉回的目录> python3.12 -B tests/nsh_candidate/oracle_check.py
# Ran 5 tests in 17.425s
# OK
```

## 4. 打包 APK 并人工走流程

```sh
"$HOME/nsh-k090/target/debug/nsh" package "$PWD/tests/nsh_candidate" --target android --abi x86_64 --run
# ✓ built the Android runtime (9m 19s)
# ✓ built libnsh.so of keex-nsh-slice for x86_64 (3m 16s)
# warn signing with the debug key: pass --keystore for store releases
# ✓ packaged .nsh/out/keex 合成实验.apk (x86_64)
# ✓ launched dev.keex.nshcandidate on emulator-5554
```

APK 38.7 MiB，包名 `dev.keex.nshcandidate`，发布版运行时，**调试密钥签名**，不是发行包。界面内容固定打进 APK，不连开发服务器。

用 `adb shell input` 的点按与按键、`uiautomator dump` 读界面文字、`screencap` 截图，在三个样本上各走一遍：

| 步骤 | 基础库 | 1k | 10k |
| --- | --- | --- | --- |
| 输入合成口令并解锁 | 摘要已加载 | 摘要已加载 | 摘要已加载 |
| 翻页 / 搜索 | 搜索 `Login` 命中“登录 Login” | 下一页、上一页 | 下一页、上一页 |
| 读取单字段 | `synthetic-user` | 空用户名 | 空用户名 |
| 修改单字段 | 单字段已修改 | 单字段已修改 | 单字段已修改 |
| 另存新副本 | 已保存新副本 | 已保存新副本 | 已保存新副本 |
| 锁库 / 切库后旧句柄 | 旧句柄已拒绝，口令与字段清空 | 切库旧句柄已拒绝 | 切库旧句柄已拒绝 |

副本落在应用私有目录 `files/nsh/dev.keex.nshcandidate/outputs/`（目录权限 700）。该 APK 不可调试，`run-as` 被拒绝；借模拟器 `userdebug` 镜像的 `adb root` 拉回三份副本，oracle 5/5 通过。应用的 `files` 目录下除这些输出外没有其他文件。

第一次走 1k / 10k 时采集脚本多点了一次“修改单字段”，副本里多出一条历史，oracle 以 `unexpected semantic changes: 1` 拒绝。修正脚本、重启应用后重走，oracle 通过。这是采集脚本的错误，不是应用缺陷；记录在此是因为它实际发生过。

第 3 节的开发宿主运行时，`output_dir()` 的条件写的是 Android 和 iOS 都走私有目录；之后收窄为只有 Android（iOS 未验证）。收窄后清空应用数据、重新打包安装，三个样本的人工流程和 oracle（5/5）用最终代码重跑通过，上表和第 5 节的 APK 数字来自这次重跑。开发宿主的 6 项测试没有用最终代码重跑：重建另外两个 ABI 需要约 30 GiB，本机磁盘不够。两者在 Android 上编译出的分支相同。

## 5. 计时（单次，不是门槛）

| 来源 | 1k | 10k |
| --- | ---: | ---: |
| 开发宿主（debug），翻页核心 `core_ms` | 0.496 | 0.331 |
| 开发宿主（debug），翻页桥接 `bridge_ms` | 4 | 3 |
| 开发宿主（debug），点按到新页可见 | 470 ms | 373 ms |
| 打包 APK（release），翻页核心 `core_ms` | 1.222 | 1.363 |
| 打包 APK（release），翻页桥接 `bridge_ms` | 6 | 8 |
| 打包 APK（release），解锁到界面出现“摘要已加载” | ≤ 2.1 s | ≤ 2.2 s |

解锁一行是 adb 轮询得到的上限，轮询本身每轮约 1.5–2 s，不能当作解锁耗时。模拟器跑在虚拟机的 KVM 上，软件渲染，数字不能外推到真机。

## 6. 观察到的问题（未修复，留给 K092 及界面实现）

- **APK 声明了 `android.permission.INTERNET`**，尽管 `nsh.json` 是 `"capabilities": {}`。应用内 `network` 请求被 NSH 拒绝（`Denied.test.tsx` 在设备上通过），但系统层面的联网权限仍在清单里。
- **清单没有设置 `allowBackup`**，按系统默认允许备份；另存的密文副本在应用数据目录内，可能进入系统备份。
- **窗口没有 `FLAG_SECURE`**（`dumpsys window` 无 SECURE 标志）：截图、录屏和最近任务缩略图可以看到界面内容。
- **口令框短暂明文显示最后一个字符**（Android 默认行为，见截图）；`uiautomator` 把该输入框标为 `password=true`。
- **标题与状态栏重叠**；软键盘弹出时遮住下半页和底部导航。
- **可访问性**：可点按的控件在无障碍树里是没有角色的 `ViewGroup`，文字在子节点上；输入框只有占位文字，没有独立名称。未用 TalkBack 实际朗读。
- 打包 APK 只导出启动 Activity；`FilesProvider` 未导出；清单里没有开发 Activity。`minSdkVersion` 26，`targetSdkVersion` 35。

## 7. 做了 / 没做 / BLOCKED

做了：SDK/NDK/模拟器用户级安装；开发宿主上 6 项 TSX 测试；打包 APK 的三样本人工流程与截图；两条路径的副本 oracle 对照；清单与窗口标志检查；中文界面显示。

没做：
- 中文输入法组字。模拟器的 Gboard 没有配置拼音；`adb shell input text` 不支持中文。测试里的中文搜索词由测试驱动直接送进输入框，不经过输入法组字。
- TalkBack 朗读、大字体、深色模式、横屏、平板、多窗口。
- 后台 / 锁屏 / 进程被杀后的会话撤销，最近任务快照内容（K092）。
- ARM ABI 的运行（`arm64-v8a`、`armeabi-v7a` 的开发宿主库已构建，没有在 ARM 设备上运行）。
- 宿主 `setGrantedCapabilities("{}")` 接线。打包 APK 用的是 NSH 自带的 `AppActivity`，没有 keex 自己的宿主代码。
- Kotlin 凭据扩展 / 自动填充服务（K007 范围，本切片不涉及）。

BLOCKED：
- Android 真机：没有设备。解除条件：提供可 adb 连接的真机，或允许使用设备云。
- 发行签名与安装验证：没有 release keystore。解除条件：提供测试用 keystore 与签名流程决定。
- 独立安全复核：需要独立审查者。

## 8. 证据文件

本机日志在 `~/k090-logs/`：`k091-android-all.log`（6 项测试）、`k091-android-package*.log`、`k091-android-apk-oracle.log`、`android-sdk-install.log`、`emulator.log`；截图在 `~/k090-logs/android-shots/`，关键截图附在 PR。日志和截图不入库。

## 9. 界面重做后的复验（2026-11-22）

实验页按 `adr/design/zh-CN/styles.css` 的深浅两套语义色重做（`theme.ts`、`ui.tsx`、`App.tsx`、`VaultPanel.tsx`）：卡片分组、分段样本选择、主次按钮、条目行、弱化的“实验检查”区。Rust 接口、会话逻辑、测试文件和全部 `testID` 未改；按钮文案改短，状态文本不变。

同一模拟器（API 35，x86_64，调试密钥 APK）上实际运行：

- 人工流程（真实触摸和按键）：基础库解锁、搜索、读取、修改、另存、锁库后旧句柄拒绝；一千条和一万条各自解锁、翻页往返、无匹配搜索、读取、修改、另存、切库旧句柄拒绝。全部通过。
- 三份副本用 `adb root` 拉回后 `oracle_check.py`：5 项通过。
- 主机：Rust 5/5，`nsh test` 11/11，主机副本 oracle 5/5，`scripts/check.py` 通过，秘密扫描测试 90 项通过。

第 6 节里本次处理掉的两项（仅在此模拟器上确认）：

- 标题不再与状态栏重叠：标题栏固定在安全区内，内容在其下滚动。软键盘弹出时聚焦的输入框保持可见；底部导航仍被键盘盖住。
- 无障碍树：按钮为 `android.widget.Button` 并带名称，三个输入框有独立名称（口令、搜索标题、用户名），导航和样本选择暴露选中状态。

另确认：跟随系统深浅色切换；横屏（宽 ≥ 760）切到同顺序侧栏。

没做：改样式后没有重跑 `nsh test --target android`（开发宿主）；TalkBack 实际朗读、大字体、平板、iOS / macOS / Windows 上的新样式均未验证。第 6 节其余各项和第 7 节的 BLOCKED 不变。
