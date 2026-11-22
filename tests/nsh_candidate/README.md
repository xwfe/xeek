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

## K091 Windows 切片复现

只验证 Windows Server 2022 虚拟机上的未签名 Win32 宿主，不计真机、签名包或其他平台通过；实际结果、缺口与 BLOCKED 项见 [K091_WINDOWS](../../adr/evidence/K091_WINDOWS.md)。

前置：Rust 1.100.0（`x86_64-pc-windows-msvc`）、VS Build Tools 2022 的 C++ 工具与 Windows SDK、LLVM/libclang、Python 3.12+、Git for Windows（以下命令在 Git Bash 中执行）。工作树须为 LF（Git for Windows 默认会转 CRLF，使设计稿摘要核对失败）；Windows 没有系统 IANA 时区库，需解压 PyPI 的 tzdata 并用 `PYTHONTZPATH` 指向其 `zoneinfo`。

```sh
export PATH="$HOME/.cargo/bin:$PATH" RUSTUP_TOOLCHAIN=1.100.0-x86_64-pc-windows-msvc
export LIBCLANG_PATH="<libclang.dll 所在目录>" PYTHONTZPATH="<tzdata 解压目录>/tzdata/zoneinfo"
git -C "$HOME/nsh-k090" rev-parse HEAD   # 必须为 2f51d8611677c8a6bbad937b39756e8d0cc45350
(cd "$HOME/nsh-k090" && cargo build --locked -p nsh-cli)
cargo fetch --locked --manifest-path tests/reference_writer/Cargo.toml
python -m pip --isolated --disable-pip-version-check install --only-binary=:all: \
  --target tests/kdbx_oracle/.deps-argon2 -r tests/kdbx_oracle/requirements.txt
PYTHONPATH=tests/kdbx_oracle/.deps-argon2 python -B -c \
  'import importlib.util; s=importlib.util.spec_from_file_location("build", "tests/wasm_core/build.py"); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.patched_source())'
cargo test --locked --manifest-path tests/nsh_candidate/rust/Cargo.toml --lib -- --nocapture --test-threads=1
export CARGO_TARGET_DIR="$HOME/nsh-k090/target"
"$HOME/nsh-k090/target/debug/nsh.exe" test "$PWD/tests/nsh_candidate" --trace
python -B tests/nsh_candidate/oracle_check.py
python -X utf8 -B scripts/check.py
```

`RUSTUP_TOOLCHAIN` 用来避免 NSH 的 `rust-toolchain.toml` 拉取滚动 stable 和交叉 target。

Win32 宿主（均未签名）：

```sh
# 开发宿主（debug，带开发服务器）
"$HOME/nsh-k090/target/debug/nsh.exe" run "$PWD/tests/nsh_candidate"
# release runner；输出目录放在仓库外。没有 Inno Setup 时只生成目录与 zip，不生成安装包
"$HOME/nsh-k090/target/debug/nsh.exe" package "$PWD/tests/nsh_candidate" --target windows -o "$HOME/k091-win/pkg"
```

启动后按 Vault.test.tsx 的同一流程手动操作：选样本 → 输入公开合成口令 → 解锁 → 翻页/搜索 → 读取首条用户名 → 修改单字段 → 再次输入口令后保存新副本 → 锁库并验证旧句柄。宿主写出的副本与 receipt 落在 `rust/target/outputs`（release runner 也写回构建机的这个路径），随后再跑一次 `oracle_check.py` 即对照 Win32 副本。

`windows/` 下三份 PowerShell 脚本经 UI Automation 观察已启动的宿主，只使用公开合成口令：

```powershell
powershell -NoProfile -File tests\nsh_candidate\windows\uia_edits.ps1 -ProcessId <pid>
powershell -NoProfile -File tests\nsh_candidate\windows\uia_tab_order.ps1 -Steps 30      # 需宿主窗口在前台
powershell -NoProfile -File tests\nsh_candidate\windows\uia_unlock_timing.ps1 -ProcessId <pid> -Label release-runner
```

计时脚本的结果含 UIA 调用与 20 ms 轮询开销，只作观测。秘密扫描 hook 不支持原生 Windows；本切片在 WSL（Linux x86_64 / CPython 3.12）中安装并从 WSL 的 git 提交，扫描命令需带 `-S`。
