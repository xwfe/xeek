# K092：Android 模拟器生命周期与宿主边界切片

日期：2026-11-22。**K092 仍为 TODO，K091 仍为 DOING。** 本文件只记录 Android 15（API 35，x86_64，`userdebug`）模拟器上的实际结果，不代表真机、ARM 设备、其他系统版本或其他平台；所有 APK 均为 debug 签名，不是发行包；没有独立安全复核。只用仓库内公开 L0 合成样本和合成口令。环境同 [K091_ANDROID](K091_ANDROID.md)。未修改 NSH 上游、核心、writer、样本或依赖。

## 1. 本切片做了什么

- 把 [K092](K092.md) 的 Linux-headless 生命周期实验并到重做后的卡片界面上（`VaultPanel.tsx` 冲突手工合并，安全逻辑不变，实验控件改为卡片和按钮）。
- `Lifecycle.test.tsx` 在设备目标上退回全屏；五类屏障用例超时放宽到 120 秒（模拟器上实际约 51 秒）。
- `VaultPanel.tsx` 监听宿主事件 `keex.revoke` 并锁库；headless 新增一项用例。
- 新增实验宿主 `tests/nsh_candidate/android_host/`：自有 Activity、清单和重新装包脚本，只用 NSH 公开嵌入接口。
- 新增 `android_host/probe.py`：用真实触摸和按键在模拟器上解锁、读取字段、触发一次系统事件，回前台后读界面状态并用保留的旧票据请求字段。

## 2. NSH 默认宿主（`nsh package` 生成的 APK）实测

`probe.py dev.keex.nshcandidate <事件>`，每个事件前强制停止并重新解锁：

| 系统事件 | 活动收到的回调 | 回前台是否已锁库 | 保留票据 |
| --- | --- | --- | --- |
| 主屏键再回来 | paused、stopped | 是 | `STALE_SESSION` |
| 熄屏再亮屏 | paused、stopped | 是 | `STALE_SESSION` |
| **最近任务再回来** | 只有 top-resumed-lost | **否** | **`ERROR_AUTH`（旧票据仍可读字段）** |
| 下拉通知栏再收起 | 无 | 否 | `ERROR_AUTH` |
| 横竖屏旋转 | 无（清单声明自行处理配置变化） | 否 | `ERROR_AUTH` |

`ERROR_AUTH` 是实验页的反例标记，表示旧票据读取成功，即授权没有被撤销。

发现：

1. **最近任务不撤权。** NSH 的 `lifecycle()` 只跟随 `ActivityLifecycleCallbacks` 的 paused/stopped；Android 15 模拟器进入最近任务时活动只失去顶层恢复态，不 pause。库保持解锁。
2. **最近任务卡片显示库内容。** 截图中任务卡片可见条目标题和“单字段已读取”状态。默认宿主没有 `FLAG_SECURE`，`adb screencap` 也能截到全部内容。
3. 清单声明 `android.permission.INTERNET`（已授予），`ALLOW_BACKUP` 标志存在，包含 `PROCESS_TEXT` 查询和 `FilesProvider`。
4. 默认 `AppActivity` 是 `final`，以 `loadAssetBundle("nsh", true)` 加载，源码注释说明“已下载的更新签名包优先运行”；没有调用 `setGrantedCapabilities`。本实验包未引入 `nsh/updater`，该路径没有被触发，也没有被验证为关闭。
5. 回前台时口令框重新获得焦点并弹出软键盘。
6. 通知栏下拉和旋转不撤权。旋转不换活动，属预期；通知栏遮挡是否应撤权是产品决定，本切片不改。

`nsh test --target android`（开发宿主）结果见第 4 节；其驱动不支持 `setLifecycle`，所以开发宿主上没有生命周期自动化，上表由 `probe.py` 经系统按键得到。

## 3. 实验宿主实测

`android_host/KeexActivity.java`（40 行）：

- `FLAG_SECURE`；
- 加载前 `setGrantedCapabilities("{}")`，返回 false 即抛错；
- `loadAssetBundle("nsh")`，不走“已下载包优先”的重载；
- `onTopResumedActivityChanged(false)` 时 `view.send("keex.revoke", null)`。

`AndroidManifest.xml`：不声明任何权限；`allowBackup="false"` 加 `dataExtractionRules`（云备份和设备迁移全部排除）；没有 `queries` 和 `FilesProvider`。

`build.py` 从 `nsh package` 产出的 APK 取 `classes.dex`、`lib/`、`assets/nsh/`，用 SDK 的 javac/d8/aapt2/zipalign/apksigner 重新装包并 debug 签名，不用 Gradle，不改 NSH。

| 检查 | 默认宿主 | 实验宿主 |
| --- | --- | --- |
| `aapt2 dump permissions` | `INTERNET` | 无 |
| `dumpsys package` 标志 | 含 `ALLOW_BACKUP` | 不含 |
| `adb screencap` | 全部内容可见 | 应用区域全黑，只剩系统栏 |
| 最近任务卡片（截图） | 可见条目标题 | 全黑 |
| 最近任务再回来 | 不锁库，`ERROR_AUTH` | 已锁库，`STALE_SESSION` |
| 主屏键、熄屏 | 已锁库，`STALE_SESSION` | 已锁库，`STALE_SESSION` |
| 通知栏、旋转 | 不撤权 | 不撤权 |

同一份界面包装进两个宿主：加入 `keex.revoke` 监听后，默认宿主上最近任务仍不撤权（对照），说明差异来自宿主。

## 4. 自动测试

| 目标 | 结果 |
| --- | --- |
| Rust 单测（主机） | 8/8 |
| `nsh test`（Linux-headless，含 `--trace`） | 21/21（8 项 Rust，13 项 TSX） |
| `nsh test --target android`（开发宿主，模拟器） | 13 项中 12 项通过，1 项失败 |
| oracle、`security_check.py`、`scripts/check.py`、秘密扫描单测 | oracle 5/5；`security_check.py` 为 pass（私有哨兵缺席、TSX 负控制仍出现）；`check.py` rc=0；秘密扫描 90/90 |

Android 失败的 1 项是“非活动后台唤醒均撤销 Rust 权限且恢复不复活”：驱动报 `setLifecycle is unsupported here: it runs headless only for now`。**这一项在 Android 上没有验证，不是通过。** 其余 12 项含五类屏障（约 50 秒）、组件销毁撤权、私有剪贴板到期与所有权、私有哨兵、TSX trace 负控制，以及新增的宿主撤权事件用例。开发宿主是 `com.longbridge.nsh.host`，不是实验宿主，也不是打包 APK。

开发宿主会为三个 ABI 各构建一份运行时，本机两次写满磁盘；最后一次用 `CARGO_PROFILE_DEV_DEBUG=0` 构建，三个 ABI 的构建目录合计约 11 GiB（此前带调试信息时约 50 GiB）。

## 5. 限制与未验证

- **`keex.revoke` 经 JS 送达。** 宿主把事件发给 NSH，TSX 监听后调用 Rust 锁库；JS 线程阻塞或界面未加载时不会执行。生产宿主应由 Kotlin 直接调用 Rust 撤权，再通知界面。本切片没有实现，也没有测量事件延迟。
- 实验宿主用 Java 写，只为不新增工具链；契约要求生产宿主用 Kotlin。
- `FLAG_SECURE` 的证据是 `adb screencap` 和最近任务截图为黑；没有用外部相机或投屏独立观察。
- `setGrantedCapabilities("{}")` 返回 true 并正常加载；没有做“界面包声明了权限、宿主拒绝”的反例，因为实验包本身声明的就是空权限。
- 嵌入模式使用 NSH 默认的嵌入限额，不是独立应用限额；一万条样本没有在实验宿主上跑。
- 实验宿主没有自行设置沉浸式状态栏；Android 15 对 target 35 强制边到边，旧系统上的布局没有看。
- 系统剪贴板没有接入（实验用 Rust 私有内存剪贴板），敏感剪贴板标记、历史和跨设备同步未验证。
- 原生安全输入未实现；口令仍经 TSX `Input`，[K092](K092.md) 记录的原始 trace 明文风险不变。
- 未验证：真机、ARM、其他系统版本、分屏/多窗口/画中画、进程被系统回收后的恢复、TalkBack、第三方输入法、Keystore 快速解锁、发行签名与安装来源。

## 6. 阻塞与解除条件

| 阻塞 | 解除条件 |
| --- | --- |
| 真机与 ARM | 可连接的 Android 真机 |
| 发行签名 | 专用测试签名密钥与签名流程授权 |
| 原生撤权路径 | 决定 Kotlin 直调 Rust 的接口形态（涉及 `VaultSession` 归属），并经独立审查 |
| 原生安全输入 | 同 [K092](K092.md) 第 3 节 |
| 独立安全复核 | 人工独立审查者 |

## 7. 复现

```sh
. ~/android-env.sh   # ANDROID_HOME、NDK、JDK、libclang，见 K091_ANDROID
mkdir -p ~/k092-pkg && cd ~/k092-pkg
"$HOME/nsh-k090/target/debug/nsh" package "$REPO/tests/nsh_candidate/SecurityApp.tsx" --target android --abi x86_64 --run
python3 "$REPO/tests/nsh_candidate/android_host/build.py" ".nsh/out/keex 合成实验.apk" \
  "$HOME/nsh-k090/target/android/debug/classes.jar" keex-host.apk
adb install -r keex-host.apk
for event in home recents screen shade rotate; do
  python3 "$REPO/tests/nsh_candidate/android_host/probe.py" dev.keex.nshcandidate "$event"
  python3 "$REPO/tests/nsh_candidate/android_host/probe.py" dev.keex.nshcandidate.host "$event"
done
```

本机日志在 `~/k090-logs/k092-android-*.log`，截图在 `~/shots/k092/`，均不入库。
