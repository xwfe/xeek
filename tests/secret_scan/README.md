# K002 本地秘密与合成样本扫描

本目录用于提交前检查和 L0 合成测试；默认扫描完整 Git 暂存区（index），另提供显式工作树检查。固定使用 Yelp detect-secrets 1.5.0 的 27 个检测器，另补 GitHub PAT、Bearer、OTP URI 和 eSIM 激活文本的四条格式规则。命中只表示需要复核，不表示凭据真实或有效。

## 安装与验证

当前哈希锁对应 **CPython 3.12 / macOS arm64**；只安装 wheel，不构建源码，不改变全局 Python 包。其他平台的 wheel 哈希与执行结果尚未验证。

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

**尚未自动安装 Git hook 或启用 CI。** 上述命令需要主动运行；未运行扫描的提交不会因此被自动阻止。依赖、扫描代码和 policy 的修改本身也需要审查。

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
- 当前登记为 95 份文件：82 KDBX、7 密钥文件、6 原始设计二进制；文本例外覆盖 30 个路径、31 个版本（同一 reader 的两个已审阅版本）。登记允许文件暂时不在某个快照；每次报告只计实际存在、摘要匹配的文件。
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
- 54 项测试（16 后端、38 门禁）覆盖正常/拒绝路径、预算、快照变化及错误脱敏。规则仍有误报和漏报；这不是生产密码学、无损 writer 或人工独立审查证据。
- 不扫描 Git 历史、其他分支、忽略的未跟踪文件、仓库外文件或编辑器缓存；已批准设计二进制只核对整体身份，不检查内部图像/归档。通过结果不提升 L0，也不表示这些位置无秘密。
