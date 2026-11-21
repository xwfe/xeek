# K002 证据：本仓库提交前扫描接入

日期：2026-10-19。任务：K002，状态仍为 **REVIEW**。数据范围：L0 公开合成。实现提交：`493376d`。

## 交付与接入

### 2026-11-21：Linux x86_64 / CPython 3.12 扩展验证

版本不变，保留所有既有哈希，仅为 PyYAML 6.0.3、charset-normalizer 3.5.2 追加 cp312-cp312 manylinux2014_x86_64/manylinux_2_17_x86_64/manylinux_2_28_x86_64 wheel 哈希。来源分别为 `https://pypi.org/pypi/PyYAML/6.0.3/json`、`https://pypi.org/pypi/charset-normalizer/3.5.2/json` 中对应 filename 的 `digests.sha256`；用 pip `download --only-binary=:all: --no-deps` 实际下载，Python hashlib 对文件字节计算，二者一致：

```text
pyyaml-6.0.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl
ba1cc08a7ccde2d2ec775841541641e4548226580ab850948cbfda66a1befcdc
charset_normalizer-3.5.2-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl
3d31298449090ab8d47b7b1b2a555ff73cac7ed438a08b7ac160980c7ebed649
```

Ubuntu x86_64 / CPython 3.12.16 使用 README 原命令的 `--require-hashes --only-binary=:all:` 安装成功，输出 `Successfully installed PyYAML-6.0.3 certifi-2026.10.18 charset-normalizer-3.5.2 detect-secrets-1.5.0 idna-3.20 requests-2.34.2 urllib3-2.8.0`。未安装全局包、未放宽 policy；公共包/许可证和替换边界不变。下述 macOS 历史结果保留，不混作 Linux 证据。

首次回归暴露后端锁解析器只接受单个 hash，追加合法 wheel hash 会触发 `DETECTOR_INIT`。最小修正为允许同一固定版本的多个 SHA-256，仍逐项验证 64 位小写十六进制，拒绝空值、畸形、重复 hash 和重复包；版本/来源检查保持。新增一项正常与错误反例回归，不修改 policy。首次新增测试过宽 mock Path.read_text 也影响依赖元数据读取，收窄 mock 后复验。

Linux 上运行 `~/.local/bin/python3.12 -B -m unittest discover -s tests/secret_scan/tests -p 'test_*.py' -v`，rc=0：`Ran 90 tests in 42.002s`、`OK`，无跳过。随后用同一解释器执行 `hooks.py install` 和 `hooks.py status`，均 rc=0、`{"status": "installed"}`；仅本仓库 `.git/hooks/pre-commit`，没有修改 Git 配置，可按 README 撤销。完整暂存树扫描 rc=0、`status=pass`、`finding_count=0`（工具成功枚举值是 pass 而非 ok）；其逐次快照摘要保留在提交回报，不把 installed 等同扫描通过。

首次有效扫描发现八项：五项为 K090 固定公开提交/锁/toolchain 摘要，三项为 test_backend.py 原有公开合成反例因新增测试导致旧文件身份失效。逐项核对前者与上游 commit/sha256sum、后者与原提交反例字节一致后，新增两个精确路径+完整摘要的 HexHighEntropyString 登记并更新该测试文件身份；没有通配豁免或关闭检测器。其余规则仍扫描。

新增 [hooks.py](../../tests/secret_scan/hooks.py) 的 install/status/uninstall，以及 [commit_hook.py](../../tests/secret_scan/commit_hook.py) 的提交入口。复用已提交的固定检测后端、Git 快照和精确登记；没有新增依赖、升级锁文件或修改 policy。操作步骤、错误码和实现边界只维护在[扫描说明](../../tests/secret_scan/README.md)。

初始只读检查确认：普通非 bare 仓库、真实 `.git` 与 hooks 目录，没有生效的 `core.hooksPath` 或既有 pre-commit。实现提交后，本仓库显式安装成功，会话 `11864077-2f88-4ad4-9ee6-8089eb67de25` 返回 `status=installed`；没有改变本机或全局 Git 配置。

本轮以真实文档提交的 hook 报告、Git 提交退出码和提交后的复核作为最后验收，不以 installed 状态代替扫描结果。最终记录归任务 `0ec6f4afd11b4fc995bc11bb6fd12cb0`。

## 回归结果：89 项全部通过

实测环境仍为 **CPython 3.12.12 / macOS arm64**。统一复现入口：

~~~sh
python3 -B -m unittest discover -s tests/secret_scan/tests -p 'test_*.py' -v
~~~

本轮分组执行，原有 54 项及新增 35 项全部通过，无跳过；只统计实际执行的扫描工具测试，不扩称其他模块也完成回归。

| 组 | 数量 | 测试报告耗时 | 实现提交前会话 |
| --- | ---: | ---: | --- |
| 原有后端与门禁 | 54 | 17.385 s | `81086d5b-2374-428d-91be-40e662ec7b9d` |
| hook 第一组 | 12 | 12.973 s | `87cdef19-e9a4-4988-8ae8-16fc5cc28cd7` |
| hook 第二组 | 12 | 17.564 s | `331e4be4-6135-48da-b489-6a30cd3bac86` |
| hook 第三组 | 11 | 17.038 s | `dcbd28de-36b6-4676-85fa-79dffed9f059` |

[新测试](../../tests/secret_scan/tests/test_hook.py) 使用一次性 Git 仓库、公开合成身份与内容，隔离用户 Git 环境和模板。临时仓库复制受测源码并链接既有固定项目依赖；结束时清理。没有测试 hook 装进其他项目，没有使用真实凭据或网络凭据验证。

| 验证对象 | 实际断言 |
| --- | --- |
| 普通提交、子目录、含空格和单引号的仓库/解释器路径 | HEAD 改变，且收到实际扫描的 pass 报告 |
| 已暂存候选、整棵树中未变更的候选 | 提交失败、HEAD 不变；工作树修正不能消除 index 中的发现 |
| 仅工作树有候选或仅工作树放宽 policy | 干净 index 可提交；未暂存 policy 不能放行 index 中的候选 |
| `--only`、`-a`、绝对/相对备用 index | 按 Git 本次准备的树判断，并核对 HEAD 内容及普通 index 的实际字节 |
| 源码与 index 不一致、源码链接、缺依赖/入口、语法错误 | 受控错误并阻断；依赖不可用时仍能撤销 |
| 导入时向 stdout/stderr 打印并 `SystemExit(0)` | 同一次提交失败、HEAD 不变、marker 不回显；退出 0 不能代替扫描完成 |
| 既有 hook、全局/本地/空值/环境 hooksPath、独立 git-dir及链接 | 拒绝接管，原文件与配置保留 |
| 重复安装/撤销、用户修改自有 hook、竞争创建/替换、受限 umask | 幂等或明确拒绝；不覆盖文件，不误报缺失/不可执行 hook 已就位 |

成功与失败路径均检查候选值、候选原路径、本机仓库路径及 traceback 不出现在受测 hook 输出中；不把它扩称为能约束 Git 自己、其他 hooks 或恶意本机代码输出。

## 先失败再修复

| 已复现的问题 | 修复 |
| --- | --- |
| 重复安装在依赖初始化后仍使用旧状态，hook 已被替换、删除或 hooksPath 已改变时可能误报 installed | 所有 install 路径重新核对配置和文件，再发布或拒绝，最后验证结果 |
| 文件创建权限被 umask 清掉，Git 会忽略不可执行 hook | 完整写入后显式设置执行权限，再发布并核对 |
| 只检查最终 Python 文件，漏掉两级入口父目录符号链接 | 读取源码和初始化后端前检查真实目录、源码与锁文件 |

初次 32 项测试有三项安装反例失败，另有一项测试误判：只读读取会更新 atime。后者改为比较身份、权限及内容变更时间，没有放宽“不覆盖旧 hook”的要求。随后补的删除竞态和两级父目录链接反例也先失败；修正后六项聚焦回归通过，会话 `11dce186-5acc-4c37-9627-9fcd6028119b`。

另修正临时依赖链接的忽略规则；没有因此放宽真实扫描。发布竞争在实际 link 操作处制造目标并发出现，断言不覆盖且无临时文件残留。方案及代码经同型号只读 agent 复核，三类实现问题均采纳；这不等于项目要求的人工独立复核。

## 暂存树与提交粒度

实现只提交安装器、提交入口、hook 测试和扫描 README 四个文件。暂存版本逐字等于审阅版本，暂存路径集合也严格只有这四个文件；`git diff --cached --check` 通过。

写入本证据及状态文档前的完整快照如下，计数仅指对应快照：

| 范围 | 文件数 | 总字节数 | 匹配批准文件 | 结果 |
| --- | ---: | ---: | --- | --- |
| 实现暂存树 | 125 | 8,570,964 | 49：37 KDBX、6 密钥、6 设计 | 0 发现 |
| 当前工作树 | 217 | 48,288,180 | 95：82 KDBX、7 密钥、6 设计 | 0 发现 |

对应会话分别为 `f33407fe-b7c6-4481-bcd7-a84a65a6069f` 与 `d5e6de99-ba7a-4eab-965c-b07d6fc82154`。本轮没有新增登记或自动刷新摘要。

另从 125 个暂存 Git blob 直接导出独立树，5 项关键真实 Git 用例及两套文档验证通过，会话 `f9706d28-37e7-40a6-80f2-9d37725224bc`。导出不经过工作树 filter，也不借用旧未提交源码；依赖仅来自既有固定安装目录。这证明实现提交可独立使用，不代表其他平台已验证。

文档只暂存共享文件中新增加的局部内容，原有 100 条未提交计划、样本及领域开发改动保留。实现与验收文档分别提交；最终提交后再核对完整 index、工作树、hook 状态和任务证据。

## 保留边界

- 每个克隆需显式启用；CI 尚未接入。覆盖会调用 pre-commit 的 `git commit`，不概括为全部自动 merge、rebase、cherry-pick 等路径。
- 本地用户可以绕过或修改 hook；源码/index 比对防意外版本不匹配，不是抵御恶意本机代码或证明执行字节身份的机制。
- 平台、预算、启发式误报/漏报及历史/非文本盲区仍按[基础扫描证据](K002_SECRETS.md)和[真实数据规则](../REAL_DATA_RULES.md)执行。
- K002 的人工复核与产品生产门槛尚未完成，L0 不变。本轮没有生产 writer、真实库接入或外部推送。

Git 官方依据：[githooks](https://git-scm.com/docs/githooks)（执行位、运行目录、退出语义及不同 hook 路径）、[core.hooksPath](https://git-scm.com/docs/git-config#Documentation/git-config.txt-corehooksPath)（有效路径配置）、[git commit](https://git-scm.com/docs/git-commit)（部分提交内容）。复核日期：2026-10-19。
