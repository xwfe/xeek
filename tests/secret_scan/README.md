# K002 本地秘密检测后端

本目录只用于开发门禁和 L0 合成测试。固定使用 Yelp detect-secrets 1.5.0 的 27 个检测器，另补 GitHub PAT、Bearer、OTP URI 和 eSIM 激活文本的四条格式规则。命中只表示需要复核，不表示凭据真实或有效。

## 安装与验证

当前哈希锁对应 **CPython 3.12 / macOS arm64**；只安装 wheel，不构建源码，不改变全局 Python 包。其他平台的 wheel 哈希与执行结果尚未验证。

~~~sh
python3 -B -m pip --isolated --disable-pip-version-check install --no-input --no-cache-dir --no-compile --only-binary=:all: --index-url https://pypi.org/simple --require-hashes --target tests/secret_scan/.deps -r tests/secret_scan/requirements.lock
python3 -B -m unittest discover -s tests/secret_scan/tests -p test_backend.py -v
~~~

安装需要下载公开包。**扫描阶段不联网**：直接对传入的文本逐行调用固定检测器，清空全部 filters，不调用凭据 verification、scan_file、baseline 或行内豁免；测试会拦截所有 detector.verify、HTTP 和 socket 创建调用。后端不读取用户凭据文件，不解密 KDBX。

依赖缺失、版本漂移、预加载模块来源不在本目录的 `.deps/` 时，返回受控错误。没有自动安装、自动更新或回退到其他版本的路径。依赖升级须同时审查规则/API变化、重新锁定 wheel、运行失败测试。

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

## 输出与豁免边界

- 后端只返回固定规则名和行号，丢弃第三方 stdout/stderr 与日志；异常只转换为固定错误码，不回显原文、原始路径或 traceback。
- Base64/Hex 熵阈值分别为 4.5/3.0，使用普通带引号模式。它们是启发式规则，存在误报与漏报。
- `PrivateKeyDetector` 只识别头标记；该版本部分令牌正则只返回捕获组。因此库里的候选摘要不能作为文件内容身份。调用方应用 `allowed_rules` 前，必须核对**确切路径和整文件 SHA-256**，不能只匹配一个私钥头或令牌前缀。
- 普通规则扫描无法证明合成来源，也不能覆盖任意编码、多行拼接、自由文字 PII、图片、归档或隐写。人工审查与真实数据规则仍适用。
- 16 项后端测试只证明以上实现边界；它不是生产密码学、无损 writer 或人工独立审查证据。
