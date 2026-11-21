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

## 待主会话执行的构建/测试

以下均是**未运行**命令（上游 AGENTS 禁止子代理 build/test/xtask，需主会话接手）。在上游根执行；用实际 keex 路径替换变量：

```sh
KEEX=/home/ubuntu/repos/xeek
cargo build --locked -p nsh-cli
./target/debug/nsh test "$KEEX/tests/nsh_candidate/App.tsx" --trace
./target/debug/nsh test "$KEEX/tests/nsh_candidate" --trace
rustup target add wasm32-unknown-unknown
cargo build --locked -p nsh-platform-web --target wasm32-unknown-unknown
./target/debug/nsh package "$KEEX/tests/nsh_candidate" --target web
```

`App.test.tsx` 覆盖正常导航和空态；`Denied.test.tsx` 独立打开 `Denied.tsx`，只认可两次 `ERR_ACCESS_DENIED`，DNS 失败或通用异常不算拒绝通过。反例使用保留的 `.invalid` 域名；权限错误地放行时仍会尝试联网，故仅在隔离的合成测试环境执行。尚无实跑输出，不作安全保证。

## 最小声明与宿主

`nsh.json` 显式 `capabilities: {}`；不省略这个字段，无 network/openUrl/fs/clipboard/windows/host 授权。Storage 不存在单独 capability；本页完全不调用 Storage。将来只能存非敏感显示偏好（如主题），不能存条目、主密码、搜索索引、密钥或同步令牌。

`host-grants.json` 是宿主接线输入，**不会因存在此文件自动生效**。K091 实现时必须在加载前传给 Android `setGrantedCapabilities("{}")`（检查 boolean）、iOS `grantCapabilities("{}")`（处理异常），或 Rust `bundle.policy.granted = Some(Capabilities::default())`；还需逐端反例验证。此处不虚构已经实现的宿主。

不配置 `updater`，不用 dev host、不加载 `.nshpkg`/远程 TSX/外部平台插件。发行须重建/审计固定 release host，只从签名资源读 bundle；不能认为 `--release` 本身关闭所有开发入口。具体源代码与缺口见证据。

`.nsh/`、根 `target/`/`build/` 已忽略；不要暂存依赖缓存、日志、SDK、运行时下载或密钥。
