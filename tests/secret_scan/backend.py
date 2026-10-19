"""固定的离线检测后端；只返回规则和行号，不返回候选值。"""
from __future__ import annotations

import contextlib
import importlib
import importlib.metadata
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEPS = HERE / ".deps"
PLUGIN_NAMES = (
    "ArtifactoryDetector", "AWSKeyDetector", "AzureStorageKeyDetector",
    "BasicAuthDetector", "CloudantDetector", "DiscordBotTokenDetector",
    "GitHubTokenDetector", "GitLabTokenDetector", "Base64HighEntropyString",
    "HexHighEntropyString", "IbmCloudIamDetector", "IbmCosHmacDetector",
    "IPPublicDetector", "JwtTokenDetector", "KeywordDetector",
    "MailchimpDetector", "NpmDetector", "OpenAIDetector", "PrivateKeyDetector",
    "PypiTokenDetector", "SendGridDetector", "SlackDetector", "SoftlayerDetector",
    "SquareOAuthDetector", "StripeDetector", "TelegramBotTokenDetector",
    "TwilioKeyDetector",
)
# 补固定发行版尚未覆盖的常见前缀；只是本地格式启发式，不判断凭据有效。
EXTRA_PATTERNS = {
    "KeexGithubPat": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{16,}\b"),
    "KeexBearerToken": re.compile(r"(?i)\bbearer[ \t]+[A-Za-z0-9_./+=-]{16,}"),
    "KeexOtpSeed": re.compile(r"(?i)\botpauth://[^\s\"'<>]*[?&]secret=[A-Z2-7]{8,}"),
    "KeexEsimActivation": re.compile(r"\bLPA:1\$[^\s\"'<>$]+\$[^\s\"'<>$]{4,}"),
}
RULES = frozenset(PLUGIN_NAMES) | EXTRA_PATTERNS.keys()
VERIFY_FILTER = "detect_secrets.filters.common.is_ignored_due_to_verification_policies"


class ScanFailure(Exception):
    """异常只携带受控码；调用方不得附带原始异常文本。"""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Hit:
    rule: str
    line: int


class _Sink:
    def write(self, value):
        return len(value)

    def flush(self):
        pass


@contextlib.contextmanager
def silence():
    # 不保留原始输出缓冲；第三方日志或异常消息可能包含候选秘密。
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with contextlib.redirect_stdout(_Sink()), contextlib.redirect_stderr(_Sink()):
            yield
    finally:
        logging.disable(previous)


def _load_dependencies():
    """只用项目安装目录；缺依赖或版本漂移不能退回环境中的其他版本。"""
    if str(DEPS) not in sys.path:
        sys.path.insert(0, str(DEPS))
    expected = {}
    for line in (HERE / "requirements.lock").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name_version, digest = line.split(" --hash=sha256:")
            name, version = name_version.split("==")
            if not re.fullmatch(r"[a-f0-9]{64}", digest) or name in expected:
                raise ScanFailure("DEPENDENCY_LOCK")
            expected[name] = version
    if expected.get("detect-secrets") != "1.5.0" or len(expected) != 7:
        raise ScanFailure("DEPENDENCY_LOCK")
    for name, version in expected.items():
        dist = importlib.metadata.distribution(name)
        if dist.version != version or not Path(dist.locate_file("")).resolve().is_relative_to(DEPS.resolve()):
            raise ScanFailure("DEPENDENCY_VERSION")
    from detect_secrets.core.log import log
    from detect_secrets.settings import get_plugins, transient_settings
    log.disabled = True
    return get_plugins, transient_settings


def _check_module_origins():
    roots = {"detect_secrets", "yaml", "requests", "charset_normalizer", "idna", "urllib3", "certifi"}
    for name in roots:
        importlib.import_module(name)
    for name, module in tuple(sys.modules.items()):
        if name.split(".")[0] in roots:
            origin = getattr(module, "__file__", None)
            if not origin or not Path(origin).resolve().is_relative_to(DEPS.resolve()):
                raise ScanFailure("DEPENDENCY_ORIGIN")


class Backend:
    """单线程本地工具；不调用 scan_file、网络验证、baseline 或行内豁免。"""

    def __enter__(self):
        entered = False
        try:
            with silence():
                get_plugins, transient_settings = _load_dependencies()
                specs = [{"name": name} for name in PLUGIN_NAMES]
                for item in specs:
                    if item["name"] == "Base64HighEntropyString":
                        item["limit"] = 4.5
                    elif item["name"] == "HexHighEntropyString":
                        item["limit"] = 3.0
                self._context = transient_settings({"plugins_used": specs, "filters_used": []})
                settings = self._context.__enter__()
                entered = True
                settings.disable_filters(*tuple(settings.filters))
                if settings.filters:
                    raise ScanFailure("DETECTOR_SETTINGS")
                self.plugins = tuple(get_plugins())
                if {type(p).__name__ for p in self.plugins} != set(PLUGIN_NAMES):
                    raise ScanFailure("DETECTOR_SETTINGS")
                _check_module_origins()
        except Exception:
            if entered:
                try:
                    with silence():
                        self._context.__exit__(None, None, None)
                except Exception:
                    pass
            raise ScanFailure("DETECTOR_INIT") from None
        return self

    def __exit__(self, *exc):
        try:
            with silence():
                self._context.__exit__(*exc)
        except Exception:
            raise ScanFailure("DETECTOR_EXIT") from None

    def scan(self, text: str, suffix: str = ".txt", allowed_rules=frozenset()):
        if not set(allowed_rules) <= RULES:
            raise ScanFailure("UNKNOWN_RULE")
        # 文件名不传给第三方；只保留语法识别需要的受控后缀。
        filename = "input" + (suffix if re.fullmatch(r"\.[A-Za-z0-9]{1,12}", suffix) else ".txt")
        try:
            for number, line in enumerate(text.splitlines(), 1):
                hits = []
                with silence():
                    for plugin in self.plugins:
                        name = type(plugin).__name__
                        if name not in allowed_rules:
                            matches = plugin.analyze_line(filename=filename, line=line, line_number=number)
                            if matches:
                                hits.append(Hit(name, number))
                    for name, pattern in EXTRA_PATTERNS.items():
                        if name not in allowed_rules and pattern.search(line):
                            hits.append(Hit(name, number))
                yield from hits
        except ScanFailure:
            raise
        except Exception:
            raise ScanFailure("DETECTOR_SCAN") from None
