# NSH 固定候选与 K091 Linux-headless 切片（仅 L0）

证据和限制见 [K090](../../adr/evidence/K090.md)、[K091](../../adr/evidence/K091.md)。本目录不是生产客户端。五导航的密码页现通过 `keex/vault` Rust class 调用原有 `tests/wasm_core`，只打开编译时固定的公开 L0 样本，不提供任意文件入口，不另写 writer/加密。手机底部五导航，宽屏同序侧栏；尚未视觉验证。

## K091 当前切片复现

仅验证 Linux-headless，不计 Android/iOS/macOS/Windows 任一端通过。使用 K090 固定版本 CLI、Rust/Cargo 1.100.0 和 Python 3.12；`rust/Cargo.toml` 的 nsh-core 使用公开 Git URL 和完整 rev 固定到下方 commit，Cargo 自行管理 checkout，不依赖本机绝对路径。CLI 必须同为该固定提交的 0.6.1；其 Rust app 生成器识别 Git 锁定 checkout，统一生成宿主与 app 的 NSH 来源，避免重复 nsh-core 类型。没有 GTK、NSH 源码或二进制入库。

从 xeek 根串行运行（首次 Cargo 下载需联网）：

```sh
git -C "$HOME/nsh-k090" rev-parse HEAD
# 必须为 2f51d8611677c8a6bbad937b39756e8d0cc45350，且源码工作树干净。
cargo fetch --locked --manifest-path tests/reference_writer/Cargo.toml
# oracle 依赖只装项目缓存；版本登记在 K091 证据，不用 macOS wheel 哈希冒充 Linux。
python3.12 -m pip --isolated --disable-pip-version-check install --only-binary=:all: \
  --target tests/kdbx_oracle/.deps-argon2 -r tests/kdbx_oracle/requirements.txt
PYTHONPATH=tests/kdbx_oracle/.deps-argon2 python3.12 -B -c \
  'import importlib.util; s=importlib.util.spec_from_file_location("build", "tests/wasm_core/build.py"); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.patched_source())'
cargo test --locked --manifest-path tests/nsh_candidate/rust/Cargo.toml --lib -- --nocapture --test-threads=1
export CARGO_TARGET_DIR="$HOME/nsh-k090/target"
"$HOME/nsh-k090/target/debug/nsh" test "$PWD/tests/nsh_candidate/Vault.test.tsx"
"$HOME/nsh-k090/target/debug/nsh" test "$PWD/tests/nsh_candidate/App.test.tsx"
"$HOME/nsh-k090/target/debug/nsh" test "$PWD/tests/nsh_candidate/Denied.test.tsx"
python3.12 -B tests/nsh_candidate/oracle_check.py
```

`patched_source()` 复用原构建入口：先核对 keepass 0.15.3 缓存归档哈希，再应用原 K003 八份补丁，输出到已忽略的 wasm_core/target/source。无需执行含 Darwin 工具链路径的整个 build.py，也不复制 core.rs。新 crate 的 Cargo.lock 固定本切片依赖；不能用它替换原 wasm_core/Cargo.lock。

`Vault.test.tsx` 驱动打开/解锁、分页和无命中搜索、单字段读取/编辑、保存新副本、锁库旧句柄拒绝、错误密码和立即取消。新副本只写 `rust/target/outputs/copy-*.kdbx`，使用 create_new；`receipt-<sample>.json` 分别指向三份固定样本的最近输出供 oracle 核对。测试不覆盖样本、不把副本入库。oracle 按登记 SHA 核对源样本，严格比较预期编辑和新增历史之外的所有语义，并以无编辑/无关修改/目标缺失作为负控制。

规模桥接增加 `Scale.test.tsx`：单独运行该文件，或用上面的同一环境运行 `nsh test "$PWD/tests/nsh_candidate" --trace`，再运行 oracle。目录命令同时执行 Rust 测试。只选择 baseline、scale-1000、scale-10000 三份编译时固定 L0 输入，切换撤销旧票据。page 返回 `{rows, coreMs}`，不返回整库。计时及边界见 K091 最新增量；render_visible 含测试驱动等待，不能当纯渲染耗时或帧率。

类型由 Rust `#[class]` / `JsObject` 生成在 `.nsh/types/keex/vault.d.ts`，不手写另一份运行时桥；列表只有 `{id,title}`、上限 50，字段单独读取，修改只开放 UserName。TSX 信号不保存整库 JSON/长期密钥，也不使用 Storage。合成口令仍经过 JS Input；masked 不构成安全输入或可擦除保证。

锁库提升 Rust epoch 并清掉当前会话；后台操作独占 Vault，结果交付再核对 binding/epoch；JS 也以 uiEpoch 丢弃已锁库的界面更新。取消是撤销交付，不是中断 KDF。已进入系统写入的密文副本可能仍落盘；不承诺原子保存取消、多进程/多窗口或进程终止恢复。详见 K091 未运行项。

导入 nsh/base 的 Input 会触发 `statusBar` 拒绝告警；已定位为显式 `{}` 生效，不是环境变量/SDK 缺失。不为消除告警扩大能力。模块里的 Rust 代码本身是受信任宿主代码，**不因空 capabilities 自动受文件沙箱约束**，故固定输入与输出目录都在 Rust 限定。

## K091 macOS / iOS 模拟器切片复现

证据、限制与 BLOCKED 见 [K091_APPLE](../../adr/evidence/K091_APPLE.md)。只算 macOS 桌面（ad hoc 包）与 iOS 模拟器；不算 iOS 真机、iPad 或其他端。需要 macOS、Xcode（含 iOS 模拟器运行时）、rustup stable、Python 3.12；不需要开发者账号。先完成上一节到 `cargo test` 为止的准备步骤，再从 xeek 根运行：

```sh
export PATH=/opt/homebrew/opt/rustup/bin:$PATH RUSTUP_TOOLCHAIN=stable-aarch64-apple-darwin
export CARGO_TARGET_DIR="$HOME/nsh-k090/target"
NSH="$HOME/nsh-k090/target/debug/nsh"   # 在 $HOME/nsh-k090 内 cargo build --locked -p nsh-cli；须为 nsh 0.6.1 (2f51d86)

# macOS AppKit 开发宿主跑 6 项 TSX 用例，再核对副本
"$NSH" test "$PWD/tests/nsh_candidate" --target macos
python3.12 -B tests/nsh_candidate/oracle_check.py -v

# iOS 模拟器开发宿主（先启动一个模拟器）
xcrun simctl boot <模拟器 UDID>; open -a Simulator   # xcrun simctl list devices 查 UDID
"$NSH" test "$PWD/tests/nsh_candidate" --target ios
python3.12 -B tests/nsh_candidate/oracle_check.py -v

# 打包后人工走流程（release runner，ad hoc 签名）
"$NSH" package "$PWD/tests/nsh_candidate" --target macos --out "$HOME/k091-apple-out/macos"
open "$HOME/k091-apple-out/macos/keex 合成实验.app"
"$NSH" package "$PWD/tests/nsh_candidate" --target ios-simulator --out "$HOME/k091-apple-out/ios-sim" --run
```

注意：

- 在 `$HOME/nsh-k090` 内运行任何 `rustup`/`cargo` 前先设置 `RUSTUP_TOOLCHAIN`。上游 `rust-toolchain.toml` 是滚动 `stable` 加 iOS/Android 目标，不设置会让 rustup 自动升级全局 stable 并安装这些目标；iOS 构建确实需要 `aarch64-apple-ios-sim`，安装前应先得到确认。
- iOS 首次构建会在 `$HOME/nsh-k090/target` 新增大量产物；本次曾因磁盘写满报 `No space left on device`，清理该目录的中间产物后通过。
- `--target ios` 不接受 `open` 的 `width`/`height`；`Vault.test.tsx`、`Scale.test.tsx` 仅在错误码为 `ERR_NSH_TEST_UNSUPPORTED` 时退回设备全屏。
- 搜索框与字段编辑框关闭了 `autoCapitalize`/`autoCorrect`：iOS 默认会把 `synthetic-nsh-edit` 改写成别的词，oracle 会以 `edit missing` 失败。
- 口令见 `tests/fixtures/kdbx` 的 manifest（公开合成值）：基础 `keex-synthetic-V41-VAULT`，规模样本 `keex-synthetic-M41-SCALE-<1000|10000>-SMALL`。人工流程每做完一个样本的“保存新副本”都会更新对应 receipt，三份都保存后再跑 oracle；重跑前删除 `rust/target/outputs`。
- 模拟器与 Mac 共用文件系统，所以模拟器里的“另存新副本”直接写进本仓库的 `rust/target/outputs`。真机没有这个路径，不能据此认为真机可保存。
- `NSH_APP_DIR` 指向外部资源目录时，打包出的 macOS runner 会加载该目录的界面与 capabilities 而不是包内资源（已实测生效）；不要把这个包当作已封闭的发行宿主。

## K091 Android 模拟器切片复现

证据与限制见 [K091_ANDROID](../../adr/evidence/K091_ANDROID.md)。只覆盖 x86_64 模拟器（API 35），不计真机。

需要 Android SDK（build-tools、`platforms;android-35`、NDK、emulator、一个 x86_64 系统镜像）、JDK 和 libclang。NDK r27 不带 libclang，bindgen 要靠 `LIBCLANG_PATH` 找到一份。磁盘至少留 60 GiB；AVD 数据分区要 12 GiB 以上，否则开发宿主 APK 装不进去。

```sh
export ANDROID_HOME="$HOME/Android/Sdk"
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"
export CARGO_TARGET_DIR="$HOME/nsh-k090/target"
export LIBCLANG_PATH=<含 libclang.so 的目录>
emulator -avd <AVD 名> -no-window -no-audio -gpu swiftshader_indirect &
adb wait-for-device

# 6 项 TSX 测试，真实触摸与按键事件
"$HOME/nsh-k090/target/debug/nsh" test "$PWD/tests/nsh_candidate" --target android

# 另存副本在开发宿主的私有目录，拉回后交给 oracle
mkdir -p /tmp/keex-android-out
for f in $(adb shell run-as com.longbridge.nsh.host find cache/nsh-test -type f | tr -d '\r'); do
  adb exec-out run-as com.longbridge.nsh.host cat "$f" > "/tmp/keex-android-out/$(basename "$f")"
done
KEEX_NSH_OUTPUTS=/tmp/keex-android-out python3.12 -B tests/nsh_candidate/oracle_check.py

# 打包并安装（调试密钥签名，不是发行包）；APK 写到当前目录的 .nsh/out，用完删除，不要入库
"$HOME/nsh-k090/target/debug/nsh" package "$PWD/tests/nsh_candidate" --target android --abi x86_64 --run
rm -rf .nsh
```

打包 APK 不可调试，副本在 `files/nsh/dev.keex.nshcandidate/outputs/`，只能在 `userdebug` 模拟器上用 `adb root` 拉回。

## 固定输入与许可证复现

上游 `https://github.com/longbridge/nsh`，tag `v0.6.1`，完整提交 `2f51d8611677c8a6bbad937b39756e8d0cc45350`，Apache-2.0。源码与构建产物放仓库外，不复制进本目录。

```sh
git clone --branch v0.6.1 https://github.com/longbridge/nsh "$HOME/nsh-k090"
git -C "$HOME/nsh-k090" rev-parse HEAD
python3.12 -B tests/nsh_candidate/inventory.py "$HOME/nsh-k090"
```

已有克隆时用固定提交的独立 worktree，不假设克隆 HEAD 就是 tag。本次 `/tmp/nsh` HEAD 实为 `4a114852947a3ed486ad90b9d2dd22a0487a15f7`，未改它；另建 `$HOME/nsh-k090` 固定 worktree。

`inventory.py` 仅运行 `cargo metadata --locked`，要求干净固定源码；首次联网下载依赖。输出 `inventory.json`（工具链原文、锁摘要、许可证表达式计数）、两份 `*-dependencies.tsv`（完整 crate/版本/许可证/source）。gpui 独立 workspace 单列。`possible` 是按 target 过滤后，从指定运行时根沿非 dev 边（含 build/proc-macro）得到的保守可达集合；workspace feature 合并可能放大，**不是成品链接或许可证法律结论**。`no` 只对这次根/target/default feature 有效，新增 feature 须重算。gpui 未被 keex 选择，故为 `not-selected`，不意味着 MPL 可以忽略。

上游 toolchain 是滚动 `stable` 而非具体版本。本次 metadata 触发 rustup 将 stable 升为 rustc/cargo 1.100.0；具体输出与锁 SHA-256 已登记。复现优先 `RUSTUP_TOOLCHAIN=1.100.0`（需用户级预装），不冒称 1.99.1 已验证。

## K090 历史构建/测试复现

以下是 K090 提交 `ca8050bc4c85cd792f8f6ea4f8c26b2356589c42` 上已通过的历史命令。复验 Web 时需在该提交的独立 xeek worktree 操作；**当前 K091 Rust 适配仅支持 native blocking，不是 Web 实现，不再宣称下面 Web 打包对当前 HEAD 成立**。目录入口由 `crates/nsh-cli/src/entry.rs:14–43` 约定为 `App.tsx`，`nsh.json` 没有 `entry` 键。

Web 编译还需要 clang 和 llvm-ar（上游 `website/docs/web.md:77–79`）；没有系统安装时，可仅在用户目录解包 Ubuntu 包，不用 sudo、不改全局环境。本次使用 clang 14.0.0-1ubuntu1.1：

```sh
# 在仓库外已有的下载目录执行（例如 $HOME/k090-logs/llvm-debs）。
apt-get download clang-14 libclang-cpp14 libllvm14 llvm-14 libclang-common-14-dev libclang1-14
mkdir -p "$HOME/.local/llvm14"
for deb in ./*.deb; do dpkg -x "$deb" "$HOME/.local/llvm14"; done
L="$HOME/.local/llvm14"
export LD_LIBRARY_PATH="$L/usr/lib/x86_64-linux-gnu:$L/usr/lib/llvm-14/lib"
export CC_wasm32_unknown_unknown="$L/usr/lib/llvm-14/bin/clang"
export AR_wasm32_unknown_unknown="$L/usr/lib/llvm-14/bin/llvm-ar"
```

包名/版本依赖 Ubuntu 发行版，以上不是跨发行版 SDK 安装器；本次实际安装/失败/输出摘要见证据。然后在上游根执行：

```sh
KEEX=/home/ubuntu/repos/xeek
cargo build --locked -p nsh-cli
./target/debug/nsh test "$KEEX/tests/nsh_candidate/App.tsx" --trace
./target/debug/nsh test "$KEEX/tests/nsh_candidate" --trace
rustup target add wasm32-unknown-unknown
cargo build --locked -p nsh-platform-web --target wasm32-unknown-unknown
./target/debug/nsh package "$KEEX/tests/nsh_candidate" --target web
```

`App.test.tsx` 覆盖正常导航和空态；`Denied.test.tsx` 独立打开 `Denied.tsx`，只认可两次 `ERR_ACCESS_DENIED`，DNS 失败或通用异常不算拒绝通过。两项均实跑通过，反例文本为“已拒绝 / 已拒绝”。反例使用保留的 `.invalid` 域名；权限错误地放行时仍会尝试联网，故仅在隔离的合成测试环境执行。headless 通过不等于原生宿主或浏览器权限验证。

Web 产物位于执行命令的上游 cwd：`.nsh/out/keex 合成实验`（5.5 MB），不在 xeek；打包声明 CSP 需要 `script-src 'self' 'wasm-unsafe-eval'; img-src 'self' blob: data:`。只放行 WASM 编译、不放行一般 `unsafe-eval`，符合 ADR-0008 的候选边界；浏览器实际加载与 CSP enforcement 留 K093。headless 底栏两字文本 frame 仅 16×17，可能受测量替身影响，K091 必须视觉核对，不据此声称排版通过。

## 最小声明与宿主

`nsh.json` 显式 `capabilities: {}`；不省略这个字段，无 network/openUrl/fs/clipboard/windows/host 授权。Storage 不存在单独 capability；本页完全不调用 Storage。将来只能存非敏感显示偏好（如主题），不能存条目、主密码、搜索索引、密钥或同步令牌。

`host-grants.json` 是宿主接线输入，**不会因存在此文件自动生效**。K091 实现时必须在加载前传给 Android `setGrantedCapabilities("{}")`（检查 boolean）、iOS `grantCapabilities("{}")`（处理异常），或 Rust `bundle.policy.granted = Some(Capabilities::default())`；还需逐端反例验证。此处不虚构已经实现的宿主。

不配置 `updater`，不用 dev host、不加载 `.nshpkg`/远程 TSX/外部平台插件。发行须重建/审计固定 release host，只从签名资源读 bundle；不能认为 `--release` 本身关闭所有开发入口。具体源代码与缺口见证据。

`.nsh/`、根 `target/`/`build/` 已忽略；不要暂存依赖缓存、日志、SDK、运行时下载或密钥。
