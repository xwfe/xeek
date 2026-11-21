# K002 本地秘密与合成样本扫描

本目录用于提交前检查和 L0 合成测试；默认扫描完整 Git 暂存区（index），另提供显式工作树检查。固定使用 Yelp detect-secrets 1.5.0 的 27 个检测器，另补 GitHub PAT、Bearer、OTP URI 和 eSIM 激活文本的四条格式规则。命中只表示需要复核，不表示凭据真实或有效。

## 安装与验证

当前哈希锁覆盖 **CPython 3.12 / macOS arm64 与 Linux x86_64**；Linux x86_64 py3.12 已验证。只安装 wheel，不构建源码，不改变全局 Python 包。其他平台尚未验证；Linux 新增哈希的来源与逐字节核对见 [K002_HOOKS](../../adr/evidence/K002_HOOKS.md)。

~~~sh
python3 -B -m pip --isolated --disable-pip-version-check install --no-input --no-cache-dir --no-compile --only-binary=:all: --index-url https://pypi.org/simple --require-hashes --target tests/secret_scan/.deps -r tests/secret_scan/requirements.lock
python3 -B -m unittest discover -s tests/secret_scan/tests -p 'test_*.py' -v
~~~

安装需要下载公开包。**扫描阶段不联网**：直接对传入的文本逐行调用固定检测器，清空全部 filters，不调用凭据 verification、scan_file、baseline 或行内豁免；测试会拦截所有 detector.verify、HTTP 和 socket 创建调用。工具只读取所选 Git 快照中的文件，不解密 KDBX。

依赖缺失、版本漂移、预加载模块来源不在本目录的 `.deps/` 时，返回受控错误。没有自动安装、自动更新或回退到其他版本的路径。依赖升级须同时审查规则/API变化、重新锁定 wheel、运行失败测试。

## 提交前运行

从仓库根目录执行：

~~~sh
python3 -B tests/secret_scan/scan.py
python3 -B tests/secret_scan/scan.py --worktree
~~~

第一条读取完整 index 的 Git blob，包含被强制加入的忽略文件；策略表也来自同一 index。应先准确暂存本次提交，再运行第一条命令。扫描后 index 变化时必须重跑。它检查整个待提交树，不只检查新增行。

第二条用于提前检查当前工作树：范围是 tracked 文件及未被忽略的 untracked 文件。读取时拒绝符号链接，并在结束前再次核对内容摘要和文件列表。工作树不是原子快照，这条命令不能替代提交前的 index 检查。

## 启用本仓库的提交钩子

安装完固定依赖后，可让普通 `git commit` 自动调用扫描器：

~~~sh
python3 -B tests/secret_scan/hooks.py install
python3 -B tests/secret_scan/hooks.py status
python3 -B tests/secret_scan/hooks.py uninstall
~~~

`install` 只创建本仓库的 `.git/hooks/pre-commit`，不改任何 Git 配置。它先验证入口和依赖能够初始化；只要有效的 `core.hooksPath` 已配置（包括全局、环境覆盖和空值），或已有不同的 pre-commit，就拒绝安装。其他 hooks 保留。重复安装相同版本不会重写文件，发布时不覆盖并发创建的文件；`uninstall` 只删除逐字匹配、身份未变的自有普通文件，不依赖扫描器或其依赖还能运行。

`status=installed` 仅表示匹配且可执行的 hook 已在位，**不表示解释器或依赖此刻可用，也不表示已完成一次扫描**。换解释器后，默认命令可能因生成的预期路径不同而返回 `HOOK_CONFLICT`；可给 `status/uninstall` 添加 `--installed-python <原解释器绝对路径>`，它只用于逐字核对旧启动器，不会执行该路径。撤销后用当前解释器重新安装。原路径可在本机查看自有 hook；不要复制个人路径到工单。

支持普通非 bare 仓库、仓库内真实 `.git` 目录与 POSIX hook；linked worktree、独立 git-dir、Git/hooks/扫描入口上的符号链接及其他平台尚不支持。启动器固定安装时的 Python 路径，正确引用空格与单引号；相对扫描入口允许移动整个仓库。Python 使用 `-I -S -B`，不加载用户 site、环境 Python 路径或 site 初始化文件，不写字节码。

提交入口保留 Git 传入的 `GIT_INDEX_FILE`，因此普通提交、`--only`、`-a` 及备用 index 都扫描 Git 为**这次提交**准备的完整树。policy 来自同一个 index；未暂存的 policy 放宽不能影响结果。入口在扫描前后核对 `commit_hook.py`、`backend.py`、`gate.py`、`snapshot.py` 和 `requirements.lock` 的工作树字节与该 index 一致；修改这些文件时需准确暂存同一版本。

缺依赖、缺入口、源码不匹配或无法完成扫描都会阻断。入口及第三方的原始输出会被抑制，启动器对无法启动等失败追加固定的 `HOOK_ABORTED` 提示。Git 自己和其他 hooks 的输出不在本工具的脱敏范围内。

| 固定码 | 处理 |
| --- | --- |
| HOOKS_PATH_CONFIGURED | 本机已有 hook 路径配置；保留它，在既有提交流程中人工接入扫描，不自动覆盖 |
| HOOK_CONFLICT / HOOK_CHANGED | hook 不同或在操作期间变化；先在本机核对，安装器不会覆盖、拼接或删除它 |
| HOOK_NOT_EXECUTABLE | 自有 hook 缺执行权限；核对后撤销并重新安装 |
| HOOK_SOURCE_MISMATCH | 扫描源码与本次 index 不一致；准确暂存同一版本后重跑 |
| HOOK_ENTRY / HOOK_RUNTIME / DETECTOR_INIT | 检查入口、固定解释器和项目内依赖；不自动下载或回退 |
| GIT_LAYOUT / HOOK_OPERATION_FAILED / HOOK_SCAN_FAILED | 检查仓库布局、文件访问及入口完整性；未完成即失败 |
| HOOK_ABORTED | 提交前扫描未通过或无法启动；结合前面的受控报告检查原因 |

每个新克隆都需显式安装；**CI 尚未启用**。范围是会调用 pre-commit 的 `git commit`，不覆盖所有自动 merge、rebase、cherry-pick 或其它生成提交的路径。用户可用 `--no-verify`、配置或修改/删除 hook 绕过它，所以这不是服务端强制门禁，也不抵御恶意本机代码。依赖、扫描代码和 policy 的修改本身仍需审查。

Git 行为依据：[githooks](https://git-scm.com/docs/githooks)、[core.hooksPath](https://git-scm.com/docs/git-config#Documentation/git-config.txt-corehooksPath)、[git commit](https://git-scm.com/docs/git-commit)。验证范围为 CPython 3.12 / macOS arm64 与 Linux x86_64。

## 扫描结果

下表为 `scan.py` 和 `commit_hook.py` 的退出码；`hooks.py` 的退出码 0 只表示管理操作完成，需查看其 JSON `status`。

| 退出码 | 含义 | 处理 |
| --- | --- | --- |
| 0 | 当前快照通过 | 快照变动后重跑 |
| 1 | 有需要复核的项目 | 在本机核对来源与内容；疑似真实秘密按[真实数据规则](../../adr/REAL_DATA_RULES.md)处理，不用新增例外消除报警 |
| 2 | 扫描未完整完成 | 根据固定错误码处理依赖、路径、快照变化或预算问题；重跑成功前不能视为通过 |

JSON 报告只输出固定规则、行号、文件 ID、计数和快照摘要，不输出候选值、原始行、原路径或第三方异常。文件 ID 是相对路径 UTF-8 的 SHA-256 前 16 位并加 `f-` 前缀；用于本机定位，不是路径加密或匿名化。不要把待核查内容复制进 agent、工单或日志。

## 精确登记与预算

`policy.json` 拒绝未知字段、重复键、重复/冲突条目、未知规则和不安全路径，不接受目录通配或行内豁免。

- 整文件批准同时绑定确切相对路径和完整 SHA-256；`kind` 只是审阅分类，程序不自动证明合成来源或解析二进制内部。只有匹配的文件才跳过内容规则；字节改变立即阻断。
- 文本例外同时绑定路径、完整 SHA-256 和明确规则，其他规则仍扫描。只写“synthetic”、沿用私钥头或令牌前缀都不能继承例外。
- 当前登记为 106 份文件：93 KDBX（含 K003 的 8 份 kdbx.dart 候选输出与 3 份官方 KeePass 合成往返）、7 密钥文件、6 原始设计二进制；文本例外覆盖 46 个路径、47 个版本（同一 reader 的两个已审阅版本）。登记允许文件暂时不在某个快照；每次报告只计实际存在、摘要匹配的文件。
- 新文件或变更必须先审阅公开合成/设计来源，再更新对应条目；没有自动刷新摘要或把扫描发现直接批准的功能。policy 的理由等自由文本也扫描，仅严格 schema 中的摘要行抑制两条熵规则误报。
- 未登记 KDBX 魔数、密钥/库备份后缀、KeePass XML、真实环境配置名以及未知二进制会阻断；不靠扩展名变更放行。`.env.example`、`.env.sample` 仍按配置语法扫描，包括无引号赋值。

| 项目 | 上限 |
| --- | ---: |
| 文件数 | 5,000 |
| Git 文件列表 | 2 MiB |
| 单文件 | 64 MiB |
| 普通文本文件 | 8 MiB |
| 单行 UTF-8 字节数 | 256 KiB |
| 全部文件字节数 | 256 MiB |
| policy | 512 KiB |

超限返回错误，不静默跳过。最多展示 50 条定位，`finding_count` 仍包含全部发现，`omitted_findings` 记录未展示数量。Git 禁用 lazy fetch、传输协议、交互提示、trace 与 fsmonitor；缺失 blob 报错，不临时联网补取。

## 依赖登记

| 包 | 固定版本 | 许可证 | 用途 |
| --- | --- | --- | --- |
| detect-secrets | 1.5.0 | Apache-2.0；部分 detector 保留 MIT 声明 | 离线关键词、格式与熵检测 |
| PyYAML | 6.0.3 | MIT | 后端要求的配置依赖 |
| requests | 2.34.2 | Apache-2.0 | 上游强制依赖；本工具不调用网络验证 |
| charset-normalizer | 3.5.2 | MIT | requests 的依赖 |
| idna | 3.20 | BSD-3-Clause | requests 的依赖 |
| urllib3 | 2.8.0 | MIT | requests 的依赖 |
| certifi | 2026.10.18 | MPL-2.0 | requests 的证书包依赖；本工具不发请求 |

版本与 wheel SHA-256 全部写入 `requirements.lock`，不只固定顶层包。上述包只用于测试工具，不进入 keex 产品。

detect-secrets 1.5.0 发布于 2024-05-06，固定 tag 对应提交 `01886c8a910c64595c47f186ca1ffc0b77fa5458`；不声称其规则及时覆盖所有新凭据。替换边界为 `backend.py` 的 `Backend.scan()` → `Hit(rule, line)`，更换后端时必须保留输出脱敏、无网络验证、逐规则豁免与失败关闭的行为。

来源：[PyPI 发行包](https://pypi.org/project/detect-secrets/1.5.0/)、[固定版本接口](https://github.com/Yelp/detect-secrets/blob/01886c8a910c64595c47f186ca1ffc0b77fa5458/detect_secrets/plugins/base.py)、[设置实现](https://github.com/Yelp/detect-secrets/blob/01886c8a910c64595c47f186ca1ffc0b77fa5458/detect_secrets/settings.py)、[许可证](https://github.com/Yelp/detect-secrets/blob/01886c8a910c64595c47f186ca1ffc0b77fa5458/LICENSE)。传递依赖的版本、许可和下载哈希来自本次 PyPI wheel 元数据。

## 检测限制

- 后端只返回固定规则名和行号，丢弃第三方 stdout/stderr 与日志；异常只转换为固定错误码，不回显原文、原始路径或 traceback。
- Base64/Hex 熵阈值分别为 4.5/3.0，使用普通带引号模式。它们是启发式规则，存在误报与漏报。
- `PrivateKeyDetector` 只识别头标记；该版本部分令牌正则只返回捕获组。因此库里的候选摘要不能作为文件内容身份。调用方应用 `allowed_rules` 前，必须核对**确切路径和整文件 SHA-256**，不能只匹配一个私钥头或令牌前缀。
- 普通规则扫描无法证明合成来源，也不能覆盖任意编码、多行拼接、自由文字 PII、图片、归档或隐写。人工审查与真实数据规则仍适用。
- 90 项测试（17 后端、38 门禁、35 hook）覆盖正常/拒绝路径、预算、快照变化、真实 Git 提交、安装/撤销保护及错误脱敏。规则仍有误报和漏报；这不是生产密码学、无损 writer 或人工独立审查证据。
- 不扫描 Git 历史、其他分支、忽略的未跟踪文件、仓库外文件或编辑器缓存；已批准设计二进制只核对整体身份，不检查内部图像/归档。通过结果不提升 L0，也不表示这些位置无秘密。
