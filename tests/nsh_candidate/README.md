# K090：NSH 固定候选（仅 L0）

证据和限制见 [K090](../../adr/evidence/K090.md)。本目录不是生产客户端，不含 KDBX、核心桥、writer 或秘密。页面仅合成标题和空态，手机底部五导航，宽屏同序侧栏；尚未视觉验证。

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

## 构建/测试复现

以下命令已在固定上游根串行执行通过；用实际 keex 路径替换变量。目录入口由 `crates/nsh-cli/src/entry.rs:14–43` 约定为 `App.tsx`，也可直接传文件路径；`nsh.json` 没有 `entry` 键，已移除首次打包时被忽略的无效键。

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
