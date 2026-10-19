"""L0 登记门禁：豁免只绑定明确路径、整文件 SHA-256 与固定规则。"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath

from backend import Backend, RULES, ScanFailure
from snapshot import MAX_LINE, MAX_TEXT, MAX_TOTAL, file_id, safe_path

POLICY_PATH = "tests/secret_scan/policy.json"
KINDS = frozenset(("synthetic-kdbx", "synthetic-key", "design-binary"))
SENSITIVE_SUFFIXES = {
    ".kdbx", ".key", ".keyx", ".pem", ".p12", ".pfx", ".passkey", ".ppk",
    ".jks", ".keystore", ".mobileprovision",
}
KEY_NAMES = {"id_rsa", "id_dsa", "id_ecdsa", "id_ecdsa_sk", "id_ed25519", "id_ed25519_sk"}
KDBX_MAGIC = bytes.fromhex("03d9a29a67fb4bb5")
XML_SPACE = re.compile(rb"\s*")
XML_ROOT = re.compile(
    rb"(?:<(?:KeePassFile|KeyFile)(?=[\s/>])|<!DOCTYPE\s+(?:KeePassFile|KeyFile)(?=[\s>\[]))"
)
DIGEST_LINE = re.compile(r'^\s*"sha256": "[a-f0-9]{64}",?\s*$')
ENTROPY_RULES = frozenset(("HexHighEntropyString", "Base64HighEntropyString"))


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ScanFailure("POLICY_DUPLICATE")
        result[key] = value
    return result


class Policy:
    def __init__(self, raw):
        try:
            obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
            if set(obj) != {"version", "approved_files", "text_exceptions"} or type(obj["version"]) is not int or obj["version"] != 1:
                raise ScanFailure("POLICY_FORMAT")
            self.approved = {}
            self.exceptions = {}
            if not isinstance(obj["approved_files"], list) or not isinstance(obj["text_exceptions"], list):
                raise ScanFailure("POLICY_FORMAT")
            for key, table, fields in (
                ("approved_files", self.approved, {"path", "sha256", "kind", "reason"}),
                ("text_exceptions", self.exceptions, {"path", "sha256", "rules", "reason"}),
            ):
                for item in obj[key]:
                    if not isinstance(item, dict) or set(item) != fields:
                        raise ScanFailure("POLICY_FORMAT")
                    path = safe_path(item["path"])
                    digest = item["sha256"]
                    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
                        raise ScanFailure("POLICY_DIGEST")
                    if not isinstance(item["reason"], str) or not item["reason"].strip():
                        raise ScanFailure("POLICY_REASON")
                    if key == "approved_files":
                        if item["kind"] not in KINDS or path in table:
                            raise ScanFailure("POLICY_DUPLICATE")
                        table[path] = (digest, item["kind"])
                    else:
                        rules = item["rules"]
                        if not isinstance(rules, list) or not rules or any(not isinstance(rule, str) for rule in rules) or len(set(rules)) != len(rules) or not set(rules) <= RULES:
                            raise ScanFailure("POLICY_RULE")
                        if (path, digest) in table or path == POLICY_PATH:
                            raise ScanFailure("POLICY_DUPLICATE")
                        table[(path, digest)] = frozenset(rules)
            if set(self.approved) & {path for path, _ in self.exceptions}:
                raise ScanFailure("POLICY_CONFLICT")
        except ScanFailure:
            raise
        except (ValueError, UnicodeError, TypeError, KeyError):
            raise ScanFailure("POLICY_FORMAT") from None

    def allowed_rules(self, path, digest):
        return self.exceptions.get((path, digest), frozenset())


def _xml_container(data):
    # 前言只向前消费；嵌套重复正则会在没有目标根时组合式回溯。
    position = 3 if data.startswith(b"\xef\xbb\xbf") else 0
    while True:
        position = XML_SPACE.match(data, position).end()
        if data.startswith(b"<?", position):
            end = data.find(b"?>", position + 2)
            width = 2
        elif data.startswith(b"<!--", position):
            end = data.find(b"-->", position + 4)
            width = 3
        else:
            return XML_ROOT.match(data, position) is not None
        if end < 0:
            return False
        position = end + width


def sensitive_container(path, data):
    name = PurePosixPath(path).name.lower()
    suffixes = {suffix.lower() for suffix in PurePosixPath(path).suffixes}
    return bool(
        suffixes & SENSITIVE_SUFFIXES or name in KEY_NAMES
        or name == ".env" or (name.startswith(".env.") and name not in (".env.example", ".env.sample"))
        or data.startswith(KDBX_MAGIC) or _xml_container(data)
    )


def inspect(snapshot, backend_factory=Backend):
    if POLICY_PATH not in snapshot.names:
        raise ScanFailure("POLICY_MISSING")
    raw_policy = snapshot.read(POLICY_PATH)
    if len(raw_policy) > 512 * 1024:
        raise ScanFailure("POLICY_SIZE_LIMIT")
    policy = Policy(raw_policy)
    report = {
        "scope": snapshot.scope, "files": len(snapshot.names), "bytes": 0,
        "text_files": 0, "approved_files": 0, "approved_kinds": {},
        "exception_files": 0, "finding_count": 0, "findings": [],
    }

    def finding(path, rule, line=0):
        report["finding_count"] += 1
        if len(report["findings"]) < 50:
            report["findings"].append({"file_id": file_id(path), "rule": rule, "line": line})

    with backend_factory() as detector:
        for path in snapshot.names:
            data = snapshot.read(path)
            report["bytes"] += len(data)
            if report["bytes"] > MAX_TOTAL:
                raise ScanFailure("TOTAL_SIZE_LIMIT")
            digest = hashlib.sha256(data).hexdigest()
            approval = policy.approved.get(path)
            if approval:
                expected, kind = approval
                if digest != expected:
                    finding(path, "APPROVED_FILE_CHANGED")
                else:
                    report["approved_files"] += 1
                    report["approved_kinds"][kind] = report["approved_kinds"].get(kind, 0) + 1
                continue
            if sensitive_container(path, data):
                finding(path, "UNREGISTERED_CONTAINER")
                continue
            if len(data) > MAX_TEXT:
                raise ScanFailure("TEXT_SIZE_LIMIT")
            try:
                text = data.decode("utf-8")
            except UnicodeError:
                finding(path, "UNREGISTERED_BINARY")
                continue
            if any(ord(char) < 32 and char not in "\t\n\r" for char in text):
                finding(path, "UNREGISTERED_BINARY")
                continue
            if any(len(line.encode("utf-8")) > MAX_LINE for line in text.splitlines()):
                raise ScanFailure("LINE_SIZE_LIMIT")
            report["text_files"] += 1
            allowed = policy.allowed_rules(path, digest)
            if allowed:
                report["exception_files"] += 1
            # 只对经过严格 schema 校验的登记表中的摘要行抑制熵误报。
            # reason 等自由文本仍扫描；普通源码的 sha256 字段不享受此例外。
            public_digest_lines = {
                n for n, line in enumerate(text.splitlines(), 1)
                if path == POLICY_PATH and DIGEST_LINE.fullmatch(line)
            }
            suffix = PurePosixPath(path).suffix
            if PurePosixPath(path).name.lower() in (".env.example", ".env.sample"):
                # 环境配置允许无引号赋值；只传受控语法后缀，不传原路径。
                suffix = ".ini"
            for hit in detector.scan(text, suffix, allowed):
                if hit.line in public_digest_lines and hit.rule in ENTROPY_RULES:
                    continue
                finding(path, hit.rule, hit.line)
    snapshot.finish()
    report["snapshot"] = snapshot.fingerprint
    report["omitted_findings"] = report["finding_count"] - len(report["findings"])
    report["status"] = "blocked" if report["finding_count"] else "pass"
    return report
