"""在项目内临时 Git 仓库验证 index、登记、失败关闭与受控输出。"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import gate
import scan
import snapshot
from backend import ScanFailure

PUBLIC = "SYNTHETIC_ONLY_NOT_VALID"
TOKEN = ("ghp" + "_" + "aB7c" * 9).encode()
PRIVATE = ("-" * 5 + "BEGIN RSA PRIVATE KEY" + "-" * 5 + "\nPUBLIC_BODY_A\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def policy_bytes(approved=(), exceptions=()):
    return (json.dumps({"version": 1, "approved_files": list(approved),
                        "text_exceptions": list(exceptions)}, indent=2) + "\n").encode()


def approve(path, data, kind="synthetic-kdbx"):
    return {"path": path, "sha256": digest(data), "kind": kind,
            "reason": "公开合成的门禁反例，只用于测试"}


def exception(path, data, rules):
    return {"path": path, "sha256": digest(data), "rules": list(rules),
            "reason": "公开合成检测标记；全文件摘要绑定"}


class PolicyTests(unittest.TestCase):
    def test_strict_schema_rejects_unknown_and_duplicate_keys(self):
        cases = (
            b'{"version":1,"version":1,"approved_files":[],"text_exceptions":[]}',
            b'{"version":true,"approved_files":[],"text_exceptions":[]}',
            b'{"version":1,"approved_files":[],"text_exceptions":[],"ignore":true}',
            b'not json',
        )
        for raw in cases:
            with self.subTest(case=digest(raw)[:8]):
                with self.assertRaises(ScanFailure):
                    gate.Policy(raw)

    def test_absolute_traversal_and_control_paths_rejected(self):
        for path in ("/absolute", "../outside", "a/../b", "a//b", "a\\b", "a\nb", ""):
            with self.subTest(case=digest(path.encode())[:8]):
                with self.assertRaises(ScanFailure):
                    gate.Policy(policy_bytes([approve(path, b"public")]))

    def test_conflicting_approvals_and_invalid_rule_rejected(self):
        value = approve("one.kdbx", b"public")
        for raw in (
            policy_bytes([value, value]),
            policy_bytes(exceptions=[exception("a.py", PRIVATE, ["bad-rule"])]),
            policy_bytes([value], [exception("one.kdbx", b"public", ["KeywordDetector"])]),
            policy_bytes(exceptions=[exception(gate.POLICY_PATH, b"public", ["KeywordDetector"])]),
        ):
            with self.assertRaises(ScanFailure):
                gate.Policy(raw)

    def test_two_explicit_text_revisions_are_distinct(self):
        first = exception("a.py", PRIVATE, ["PrivateKeyDetector"])
        second = exception("a.py", PRIVATE + b"PUBLIC_B", ["PrivateKeyDetector"])
        policy = gate.Policy(policy_bytes(exceptions=[first, second]))
        self.assertEqual(policy.allowed_rules("a.py", first["sha256"]), {"PrivateKeyDetector"})
        self.assertEqual(policy.allowed_rules("a.py", digest(b"changed")), frozenset())

    def test_invalid_digest_and_empty_reason_rejected(self):
        for field, value in (("sha256", "invalid"), ("reason", ""), ("kind", "unknown")):
            item = approve("test.kdbx", b"public")
            item[field] = value
            with self.assertRaises(ScanFailure):
                gate.Policy(policy_bytes([item]))


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        scratch = HERE / ".scratch"
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="case-", dir=scratch)
        self.root = Path(self.temp.name)
        env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
        env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
        self.environ = patch.dict(os.environ, env, clear=True)
        self.environ.start()
        self.git("-c", "init.templateDir=", "-c", "core.hooksPath=" + os.devnull, "init", "-q")
        self.write(gate.POLICY_PATH, policy_bytes())

    def tearDown(self):
        self.environ.stop()
        self.temp.cleanup()

    def git(self, *args, input=None):
        result = subprocess.run(
            ["git", *args], cwd=self.root, env=os.environ, input=input,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20,
        )
        self.assertEqual(result.returncode, 0, "temporary Git setup failed")
        return result.stdout

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def stage(self):
        self.git("add", "--", ".")

    def inspect(self, scope="index"):
        return gate.inspect(snapshot.Snapshot(self.root, scope))

    def rules(self, result):
        return {hit["rule"] for hit in result["findings"]}

    def test_clean_index_passes(self):
        self.write("a.txt", b"ordinary example\n")
        self.stage()
        result = self.inspect()
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["files"], 2)
        self.assertEqual(result["scope"], "index")

    def test_staged_secret_survives_worktree_correction(self):
        self.write("a.txt", TOKEN)
        self.stage()
        self.write("a.txt", b"ordinary\n")
        self.assertIn("GitHubTokenDetector", self.rules(self.inspect()))
        self.assertEqual(self.inspect("worktree")["status"], "pass")

    def test_clean_staged_version_not_replaced_by_worktree_secret(self):
        self.write("a.txt", b"ordinary\n")
        self.stage()
        self.write("a.txt", TOKEN)
        self.assertEqual(self.inspect()["status"], "pass")
        self.assertIn("GitHubTokenDetector", self.rules(self.inspect("worktree")))

    def test_policy_is_read_from_same_index(self):
        self.write("fixture.py", PRIVATE)
        self.stage()
        self.write(gate.POLICY_PATH, policy_bytes(exceptions=[
            exception("fixture.py", PRIVATE, ["PrivateKeyDetector"]),
        ]))
        self.assertIn("PrivateKeyDetector", self.rules(self.inspect()))
        self.assertEqual(self.inspect("worktree")["status"], "pass")

    def test_index_policy_can_allow_exact_bytes_without_worktree_policy(self):
        self.write("fixture.py", PRIVATE)
        self.write(gate.POLICY_PATH, policy_bytes(exceptions=[
            exception("fixture.py", PRIVATE, ["PrivateKeyDetector"]),
        ]))
        self.stage()
        self.write(gate.POLICY_PATH, policy_bytes())
        self.assertEqual(self.inspect()["status"], "pass")
        self.assertIn("PrivateKeyDetector", self.rules(self.inspect("worktree")))

    def test_same_marker_changed_body_and_added_marker_lose_approval(self):
        self.write("fixture.py", PRIVATE)
        self.write(gate.POLICY_PATH, policy_bytes(exceptions=[
            exception("fixture.py", PRIVATE, ["PrivateKeyDetector"]),
        ]))
        self.stage()
        self.assertEqual(self.inspect()["status"], "pass")
        for changed in (PRIVATE.replace(b"BODY_A", b"BODY_B"), PRIVATE + PRIVATE):
            self.write("fixture.py", changed)
            self.stage()
            self.assertIn("PrivateKeyDetector", self.rules(self.inspect()))

    def test_same_github_prefix_changed_body_loses_approval(self):
        self.write("fixture.txt", TOKEN)
        self.write(gate.POLICY_PATH, policy_bytes(exceptions=[
            exception("fixture.txt", TOKEN, ["GitHubTokenDetector"]),
        ]))
        self.stage()
        self.assertEqual(self.inspect()["status"], "pass")
        self.write("fixture.txt", TOKEN[:-1] + b"Z")
        self.stage()
        self.assertIn("GitHubTokenDetector", self.rules(self.inspect()))

    def test_copy_to_new_path_does_not_inherit_approval(self):
        self.write("fixture.py", PRIVATE)
        self.write("other.py", PRIVATE)
        self.write(gate.POLICY_PATH, policy_bytes(exceptions=[
            exception("fixture.py", PRIVATE, ["PrivateKeyDetector"]),
        ]))
        self.stage()
        result = self.inspect()
        self.assertIn("PrivateKeyDetector", self.rules(result))
        self.assertTrue(any(hit["file_id"] == snapshot.file_id("other.py") for hit in result["findings"]))

    def test_unknown_kdbx_magic_and_backup_extension_rejected(self):
        for path, data in (
            ("renamed.txt", gate.KDBX_MAGIC + b"PUBLIC"),
            ("vault.KDBX.bak", b"ordinary"),
            ("vault.keyx", b"ordinary"),
        ):
            self.write(path, data)
        self.stage()
        result = self.inspect()
        self.assertEqual(result["finding_count"], 3)
        self.assertEqual(self.rules(result), {"UNREGISTERED_CONTAINER"})

    def test_encrypted_file_approval_requires_path_and_hash(self):
        data = gate.KDBX_MAGIC + b"PUBLIC_A"
        self.write("fixture.kdbx", data)
        self.write(gate.POLICY_PATH, policy_bytes([approve("fixture.kdbx", data)]))
        self.stage()
        result = self.inspect()
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["approved_kinds"], {"synthetic-kdbx": 1})
        self.write("fixture.kdbx", data + b"PUBLIC_B")
        self.stage()
        self.assertEqual(self.rules(self.inspect()), {"APPROVED_FILE_CHANGED"})

    def test_missing_optional_registered_file_does_not_claim_it_was_scanned(self):
        self.write(gate.POLICY_PATH, policy_bytes([approve("not-present.kdbx", b"PUBLIC")]))
        self.stage()
        result = self.inspect()
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["approved_files"], 0)

    def test_xml_prolog_variations_are_containers(self):
        values = (
            b"<KeePassFile/>", b"<KeyFile/>",
            b"<?xml version='1.0'?><!-- public --><KeePassFile/>",
            b"<?public test?><!-- public --><KeyFile/>",
            b"<!DOCTYPE KeePassFile [<!ELEMENT KeePassFile ANY>]><KeePassFile/>",
        )
        for number, value in enumerate(values):
            self.write("export" + str(number) + ".txt", value)
        self.stage()
        result = self.inspect()
        self.assertEqual(result["finding_count"], len(values))
        self.assertEqual(self.rules(result), {"UNREGISTERED_CONTAINER"})

    def test_unknown_binary_invalid_utf8_and_utf16_fail(self):
        for number, data in enumerate((b"\x00public", b"\xffpublic", "public".encode("utf-16"))):
            self.write("data" + str(number) + ".bin", data)
        self.stage()
        result = self.inspect()
        self.assertEqual(result["finding_count"], 3)
        self.assertEqual(self.rules(result), {"UNREGISTERED_BINARY"})

    def test_env_examples_still_scan_and_real_env_name_denied(self):
        for name in (".env.example", ".env.sample"):
            for quoted in (False, True):
                with self.subTest(name=name, quoted=quoted):
                    value = ('"' + PUBLIC + '"') if quoted else PUBLIC
                    path = self.write(name, ("api_key=" + value).encode())
                    self.stage()
                    self.assertIn("KeywordDetector", self.rules(self.inspect()))
                    path.unlink()
                    self.git("rm", "--cached", "--", name)
        self.write(".env", b"ordinary")
        self.stage()
        self.assertEqual(self.rules(self.inspect()), {"UNREGISTERED_CONTAINER"})

    def test_xml_repeated_preludes_complete_within_budget(self):
        script = (
            "import gate\n"
            "for prefix in (b'<?public?>', b'<!-- public -->', b'<?public?><!-- public -->'):\n"
            "    value = prefix * 4096\n"
            "    assert not gate.sensitive_container('ordinary.txt', value + b'ordinary')\n"
            "    assert gate.sensitive_container('ordinary.txt', value + b'<KeyFile/>')\n"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", script], cwd=HERE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
        )
        self.assertEqual(result.returncode, 0, "XML prelude scan failed")

    def test_ignored_untracked_skipped_but_force_added_scanned(self):
        self.write(".gitignore", b"*.env\n")
        self.write("ignored.env", TOKEN)
        self.stage()
        self.assertEqual(self.inspect("worktree")["status"], "pass")
        self.git("add", "-f", "--", "ignored.env")
        self.assertIn("GitHubTokenDetector", self.rules(self.inspect()))

    def test_deleted_worktree_file_still_scanned_in_index(self):
        path = self.write("a.txt", TOKEN)
        self.stage()
        path.unlink()
        self.assertIn("GitHubTokenDetector", self.rules(self.inspect()))
        self.git("rm", "--", "a.txt")
        self.assertEqual(self.inspect()["status"], "pass")

    def test_index_conflict_and_gitlink_are_rejected(self):
        oid = self.git("hash-object", "-w", "--stdin", input=b"public").strip()
        self.git("update-index", "--index-info", input=b"100644 " + oid + b" 1\tconflict.txt\n")
        with self.assertRaisesRegex(ScanFailure, "^INDEX_CONFLICT$"):
            snapshot.Snapshot(self.root, "index")
        self.git("update-index", "--force-remove", "--", "conflict.txt")
        self.git("update-index", "--index-info", input=b"160000 " + oid + b"\tsubmodule\n")
        with self.assertRaisesRegex(ScanFailure, "^UNSUPPORTED_MODE$"):
            snapshot.Snapshot(self.root, "index")

    def test_symlink_and_parent_symlink_not_followed(self):
        target = self.write("ordinary.txt", b"public")
        (self.root / "link.txt").symlink_to(target)
        self.stage()
        with self.assertRaisesRegex(ScanFailure, "^UNSUPPORTED_MODE$"):
            snapshot.Snapshot(self.root, "index")
        with self.assertRaisesRegex(ScanFailure, "^FILE_READ$"):
            self.inspect("worktree")
        (self.root / "link.txt").unlink()
        self.git("rm", "--cached", "--", "link.txt")
        directory = self.root / "dir"
        directory.mkdir()
        self.write("dir/file.txt", b"public")
        self.stage()
        (directory / "file.txt").unlink()
        directory.rmdir()
        directory.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ScanFailure, "^FILE_READ$"):
            self.inspect("worktree")

    def test_index_change_during_scan_rejected(self):
        self.write("a.txt", b"public")
        self.stage()
        current = snapshot.Snapshot(self.root, "index")
        self.write("a.txt", b"changed")
        self.stage()
        with self.assertRaisesRegex(ScanFailure, "^SNAPSHOT_CHANGED$"):
            gate.inspect(current)

    def test_worktree_change_after_read_rejected(self):
        self.write("a.txt", b"public")
        self.stage()
        current = snapshot.Snapshot(self.root, "worktree")
        current.read("a.txt")
        self.write("a.txt", b"changed")
        with self.assertRaisesRegex(ScanFailure, "^WORKTREE_CHANGED$"):
            current.finish()

    def test_alternate_index_is_respected(self):
        self.write("a.txt", b"public")
        self.stage()
        alternate = self.root / ".git" / "alternate-index"
        alternate.write_bytes((self.root / ".git" / "index").read_bytes())
        self.write("a.txt", TOKEN)
        with patch.dict(os.environ, {"GIT_INDEX_FILE": str(alternate)}):
            self.stage()
            self.assertIn("GitHubTokenDetector", self.rules(self.inspect()))
        self.assertEqual(self.inspect()["status"], "pass")

    def test_snapshot_limits_fail_closed(self):
        self.write("a.txt", b"x" * 600)
        self.stage()
        with patch.object(snapshot, "MAX_FILES", 1):
            with self.assertRaisesRegex(ScanFailure, "^FILE_COUNT_LIMIT$"):
                snapshot.Snapshot(self.root, "index")
        for module, name, limit, code in (
            (snapshot, "MAX_FILE", 500, "FILE_SIZE_LIMIT"),
            (gate, "MAX_TEXT", 500, "TEXT_SIZE_LIMIT"),
            (gate, "MAX_TOTAL", 500, "TOTAL_SIZE_LIMIT"),
            (gate, "MAX_LINE", 500, "LINE_SIZE_LIMIT"),
        ):
            with self.subTest(code=code), patch.object(module, name, limit):
                with self.assertRaisesRegex(ScanFailure, "^" + code + "$"):
                    self.inspect()

    def test_relative_alternate_index_from_subdirectory(self):
        self.write("a.txt", b"public")
        self.stage()
        alternate = self.root / ".git" / "alternate-index"
        alternate.write_bytes((self.root / ".git" / "index").read_bytes())
        self.write("a.txt", TOKEN)
        with patch.dict(os.environ, {"GIT_INDEX_FILE": str(alternate)}):
            self.stage()
        child = self.root / "child"
        child.mkdir()
        previous = Path.cwd()
        try:
            os.chdir(child)
            with patch.dict(os.environ, {"GIT_INDEX_FILE": "../.git/alternate-index"}):
                self.assertIn("GitHubTokenDetector", self.rules(self.inspect()))
        finally:
            os.chdir(previous)
        self.assertEqual(self.inspect()["status"], "pass")

    def test_alternate_index_symlink_retarget_is_detected(self):
        self.write("a.txt", b"public")
        self.stage()
        clean = self.root / ".git" / "clean-index"
        clean.write_bytes((self.root / ".git" / "index").read_bytes())
        self.write("a.txt", TOKEN)
        self.stage()
        dirty = self.root / ".git" / "dirty-index"
        dirty.write_bytes((self.root / ".git" / "index").read_bytes())
        active = self.root / ".git" / "active-index"
        active.symlink_to(clean)
        with patch.dict(os.environ, {"GIT_INDEX_FILE": str(active)}):
            current = snapshot.Snapshot(self.root, "index")
            active.unlink()
            active.symlink_to(dirty)
            with self.assertRaisesRegex(ScanFailure, "^SNAPSHOT_CHANGED$"):
                gate.inspect(current)

    def test_worktree_digest_catches_same_length_and_restored_mtime(self):
        path = self.write("a.txt", b"public-A")
        self.stage()
        current = snapshot.Snapshot(self.root, "worktree")
        current.read("a.txt")
        previous = path.stat()
        path.write_bytes(b"public-B")
        os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
        with self.assertRaisesRegex(ScanFailure, "^WORKTREE_CHANGED$"):
            current.finish()

    def test_large_text_over_two_megabytes_is_actually_scanned(self):
        self.write("large.txt", b"ordinary line\n" * 165000 + TOKEN)
        self.stage()
        self.assertIn("GitHubTokenDetector", self.rules(self.inspect()))

    def test_findings_cap_still_reports_total(self):
        self.write("tokens.txt", (TOKEN + b"\n") * 60)
        self.stage()
        result = self.inspect()
        self.assertEqual(len(result["findings"]), 50)
        self.assertEqual(result["finding_count"], 60)
        self.assertEqual(result["omitted_findings"], 10)

    def test_policy_free_text_is_scanned(self):
        value = approve("optional.kdbx", b"public")
        value["reason"] = TOKEN.decode()
        self.write(gate.POLICY_PATH, policy_bytes([value]))
        self.stage()
        self.assertIn("GitHubTokenDetector", self.rules(self.inspect()))

    def test_untrusted_path_and_values_not_echoed_by_cli(self):
        name = PUBLIC + ".txt"
        self.write(name, TOKEN)
        self.stage()
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = scan.main(["--root", str(self.root)])
        value = stdout.getvalue()
        self.assertEqual(code, 1)
        self.assertTrue(PUBLIC not in value and TOKEN.decode() not in value)
        self.assertTrue(stderr.getvalue() == "")
        self.assertEqual(json.loads(value)["status"], "blocked")

    def test_cli_usage_and_unexpected_exception_do_not_echo(self):
        for args, mocked in (
            (["--" + PUBLIC], False),
            (["--root", str(self.root)], True),
        ):
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.ExitStack() as stack:
                stack.enter_context(contextlib.redirect_stdout(stdout))
                stack.enter_context(contextlib.redirect_stderr(stderr))
                if mocked:
                    stack.enter_context(patch.object(scan, "inspect", side_effect=RuntimeError(PUBLIC)))
                code = scan.main(args)
            self.assertEqual(code, 2)
            self.assertTrue(PUBLIC not in stdout.getvalue() + stderr.getvalue())
            self.assertTrue(stderr.getvalue() == "")

    def test_missing_policy_or_blob_is_an_error(self):
        self.git("add", "--", gate.POLICY_PATH)
        self.git("rm", "--cached", "--", gate.POLICY_PATH)
        with self.assertRaisesRegex(ScanFailure, "^POLICY_MISSING$"):
            self.inspect()
        self.stage()
        oid = self.git("hash-object", "-w", "--stdin", input=b"public orphan").decode().strip()
        self.git("update-index", "--index-info", input=("100644 " + oid + "\torphan.txt\n").encode())
        (self.root / ".git" / "objects" / oid[:2] / oid[2:]).unlink()
        with self.assertRaisesRegex(ScanFailure, "^GIT_COMMAND$"):
            self.inspect()

    def test_git_environment_disables_transport_and_lazy_fetch(self):
        self.stage()
        real_run = subprocess.run
        with patch.object(snapshot.subprocess, "run", wraps=real_run) as calls:
            self.inspect()
        self.assertTrue(all(
            call.kwargs["env"].get("GIT_NO_LAZY_FETCH") == "1"
            and call.kwargs["env"].get("GIT_ALLOW_PROTOCOL") == ""
            and call.kwargs["env"].get("GIT_TERMINAL_PROMPT") == "0"
            for call in calls.call_args_list
        ))


if __name__ == "__main__":
    unittest.main()
