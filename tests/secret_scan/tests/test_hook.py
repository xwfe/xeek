"""只用公开合成内容和临时 Git 仓库验证真正的提交行为。"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import hooks

TOKEN = ("ghp" + "_" + "aB7c" * 9).encode()
CANDIDATE = "public-candidate.txt"
SOURCE_NAMES = ("hooks.py", "commit_hook.py", "backend.py", "gate.py", "snapshot.py", "requirements.lock")


def unchanged_metadata(path):
    # 只读操作可更新 atime；身份、权限与内容变更时间必须保持。
    value = path.stat()
    return tuple(getattr(value, name) for name in
                 ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns"))


class HookTests(unittest.TestCase):
    def setUp(self):
        scratch = HERE / ".scratch"
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="hook-", dir=scratch)
        self.root = Path(self.temp.name) / "repository's space"
        self.root.mkdir()
        self.addCleanup(self.temp.cleanup)
        env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_TERMINAL_PROMPT="0", GIT_ALLOW_PROTOCOL="")
        self.environment = patch.dict(os.environ, env, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.git("-c", "init.templateDir=", "init", "-q")
        self.git("config", "--local", "user.name", "SYNTHETIC_ONLY")
        self.git("config", "--local", "user.email", "user@example.com")
        self.git("config", "--local", "commit.gpgSign", "false")
        self.here = self.root / "tests/secret_scan"
        self.here.mkdir(parents=True)
        for name in SOURCE_NAMES:
            shutil.copyfile(HERE / name, self.here / name)
        (self.here / ".deps").symlink_to(HERE / ".deps", target_is_directory=True)
        # 只复用已审阅 gate 源码的整文件例外，不自动批准本轮检测器发现。
        policy = json.loads((HERE / "policy.json").read_text())
        policy["approved_files"] = []
        policy["text_exceptions"] = [item for item in policy["text_exceptions"]
                                     if item["path"] == "tests/secret_scan/gate.py"]
        self.policy = policy
        self.write_policy()
        self.write(".gitignore", b"/tests/secret_scan/.deps\n")
        self.write(CANDIDATE, b"ordinary public text\n")
        self.write("safe.txt", b"ordinary public text\n")
        self.git("add", "--", ".")
        self.git("commit", "-q", "-m", "public synthetic baseline")
        self.hook = self.root / ".git/hooks/pre-commit"

    def command(self, argv, cwd=None, env=None):
        return subprocess.run(
            argv, cwd=cwd or self.root, env=env or os.environ, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25, check=False,
        )

    def git(self, *args):
        result = self.command(["git", *args])
        self.assertEqual(result.returncode, 0, "temporary Git setup failed")
        return result.stdout

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def write_policy(self):
        return self.write("tests/secret_scan/policy.json",
                          (json.dumps(self.policy, indent=2) + "\n").encode())

    def manage(self, action, *args, expected=0, executable=None, env=None):
        result = self.command(
            [str(executable or sys.executable), "-I", "-S", "-B", str(self.here / "hooks.py"), action, *args],
            env=env,
        )
        self.assertEqual(result.returncode, expected, "hook operation returned unexpected code")
        self.assert_redacted(result)
        self.assertFalse(result.stderr, "hook CLI wrote uncontrolled stderr")
        return json.loads(result.stdout)

    def install(self):
        self.assertEqual(self.manage("install")["status"], "installed")

    def assert_redacted(self, result, forbidden=()):
        output = result.stdout + result.stderr
        for value in (TOKEN, CANDIDATE.encode(), str(self.root).encode(), b"Traceback", *forbidden):
            self.assertTrue(value not in output, "candidate, path or traceback leaked")

    def commit(self, *args, blocked=False, code=None, cwd=None, env=None, forbidden=()):
        before = self.git("rev-parse", "HEAD")
        result = self.command(["git", "commit", "-q", "-m", "public synthetic change", *args],
                              cwd=cwd, env=env)
        self.assert_redacted(result, forbidden)
        if blocked:
            self.assertNotEqual(result.returncode, 0, "unsafe commit succeeded")
            self.assertEqual(self.git("rev-parse", "HEAD"), before, "blocked commit changed HEAD")
        else:
            self.assertEqual(result.returncode, 0, "safe commit was blocked")
            self.assertNotEqual(self.git("rev-parse", "HEAD"), before, "commit was not created")
        reports = [json.loads(line) for line in (result.stdout + result.stderr).splitlines()
                   if line.startswith(b"{")]
        if code:
            self.assertTrue(any(item.get("code") == code for item in reports),
                            "expected controlled error absent")
        if not blocked:
            self.assertTrue(any(item.get("status") == "pass" for item in reports),
                            "commit did not execute the gate")
        return reports

    def changed_safe_file(self):
        self.write("safe.txt", b"another ordinary line\n")
        self.git("add", "--", "safe.txt")

    def test_clean_commit_from_subdirectory_and_quoted_repository_path(self):
        self.install()
        self.changed_safe_file()
        self.commit(cwd=self.here)

    def test_staged_candidate_blocks_even_when_worktree_is_fixed(self):
        self.install()
        self.write(CANDIDATE, TOKEN)
        self.git("add", "--", CANDIDATE)
        self.write(CANDIDATE, b"ordinary public correction\n")
        reports = self.commit(blocked=True)
        self.assertTrue(any(item.get("status") == "blocked" for item in reports))

    def test_unstaged_candidate_does_not_block_clean_index(self):
        self.install()
        self.write(CANDIDATE, TOKEN)
        self.changed_safe_file()
        self.commit()
        self.assertEqual(self.git("show", "HEAD:" + CANDIDATE), b"ordinary public text\n")

    def test_unchanged_candidate_in_full_tree_blocks_new_document(self):
        self.write(CANDIDATE, TOKEN)
        self.git("add", "--", CANDIDATE)
        self.git("commit", "-q", "-m", "public negative baseline")
        self.install()
        self.changed_safe_file()
        self.commit(blocked=True)

    def add_public_exception(self):
        self.policy["text_exceptions"].append({
            "path": CANDIDATE, "sha256": hashlib.sha256(TOKEN).hexdigest(),
            "rules": ["GitHubTokenDetector"], "reason": "公开合成的本地提交反例",
        })
        self.write_policy()

    def test_worktree_policy_relaxation_cannot_bypass_index(self):
        self.install()
        self.write(CANDIDATE, TOKEN)
        self.git("add", "--", CANDIDATE)
        self.add_public_exception()
        self.commit(blocked=True)

    def test_staged_policy_is_used_when_worktree_policy_differs(self):
        self.install()
        original = (self.here / "policy.json").read_bytes()
        self.write(CANDIDATE, TOKEN)
        self.add_public_exception()
        self.git("add", "--", CANDIDATE, "tests/secret_scan/policy.json")
        (self.here / "policy.json").write_bytes(original)
        self.commit()

    def test_alternate_index_blocks_candidate_and_preserves_default_index(self):
        self.install()
        alternate = self.root / ".git/alternate-index"
        shutil.copyfile(self.root / ".git/index", alternate)
        self.write(CANDIDATE, TOKEN)
        with patch.dict(os.environ, {"GIT_INDEX_FILE": str(alternate)}):
            self.git("add", "--", CANDIDATE)
        original_index = (self.root / ".git/index").read_bytes()
        env = dict(os.environ, GIT_INDEX_FILE=str(alternate))
        self.commit(blocked=True, env=env)
        self.assertEqual((self.root / ".git/index").read_bytes(), original_index)

    def test_clean_relative_alternate_index_ignores_dirty_default_index(self):
        self.install()
        alternate = self.root / ".git/alternate-index"
        shutil.copyfile(self.root / ".git/index", alternate)
        self.write(CANDIDATE, TOKEN)
        self.git("add", "--", CANDIDATE)
        self.write("safe.txt", b"another ordinary line\n")
        with patch.dict(os.environ, {"GIT_INDEX_FILE": ".git/alternate-index"}):
            self.git("add", "--", "safe.txt")
        self.commit(env=dict(os.environ, GIT_INDEX_FILE=".git/alternate-index"))
        self.assertEqual(self.git("show", "HEAD:" + CANDIDATE), b"ordinary public text\n")
        self.assertEqual(self.git("show", ":" + CANDIDATE), TOKEN)

    def test_only_safe_path_ignores_other_staged_candidate(self):
        self.install()
        self.write(CANDIDATE, TOKEN)
        self.git("add", "--", CANDIDATE)
        self.write("safe.txt", b"another ordinary line\n")
        self.commit("--only", "--", "safe.txt")
        self.assertEqual(self.git("show", "HEAD:" + CANDIDATE), b"ordinary public text\n")
        self.assertEqual(self.git("show", ":" + CANDIDATE), TOKEN)
        self.commit(blocked=True)

    def test_only_candidate_path_scans_worktree_version_prepared_by_git(self):
        self.install()
        self.write(CANDIDATE, TOKEN)
        self.commit("--only", "--", CANDIDATE, blocked=True)

    def test_commit_all_scans_worktree_version_prepared_by_git(self):
        self.install()
        self.write(CANDIDATE, TOKEN)
        self.commit("-a", blocked=True)

    def test_unstaged_scanner_change_blocks_then_matching_source_commits(self):
        self.install()
        path = self.here / "commit_hook.py"
        path.write_bytes(path.read_bytes() + b"\n# public implementation change\n")
        self.changed_safe_file()
        self.commit(blocked=True, code="HOOK_SOURCE_MISMATCH")
        self.git("add", "--", "tests/secret_scan/commit_hook.py")
        self.commit()

    def test_staged_scanner_change_blocks_old_worktree_source(self):
        self.install()
        path = self.here / "backend.py"
        original = path.read_bytes()
        path.write_bytes(original + b"\n# public implementation change\n")
        self.git("add", "--", "tests/secret_scan/backend.py")
        path.write_bytes(original)
        self.commit(blocked=True, code="HOOK_SOURCE_MISMATCH")

    def test_missing_dependencies_block_commit_but_allow_uninstall(self):
        self.install()
        (self.here / ".deps").unlink()
        self.changed_safe_file()
        self.commit(blocked=True, code="DETECTOR_INIT")
        self.assertEqual(self.manage("uninstall")["status"], "absent")

    def test_missing_entry_or_import_and_invalid_source_block_without_traceback(self):
        self.install()
        self.changed_safe_file()
        for name in ("commit_hook.py", "gate.py"):
            path = self.here / name
            original = path.read_bytes()
            with self.subTest(module=name, fault="missing"):
                path.unlink()
                self.commit(blocked=True, code="HOOK_ABORTED")
                path.write_bytes(original)
            with self.subTest(module=name, fault="syntax"):
                path.write_bytes(b"invalid Python !\n")
                self.commit(blocked=True, code="HOOK_ABORTED")
                path.write_bytes(original)

    def test_source_symlink_is_rejected(self):
        self.install()
        path = self.here / "requirements.lock"
        original = path.read_bytes()
        copy = self.write(".git/public-lock-copy", original)
        path.unlink()
        path.symlink_to(copy)
        self.changed_safe_file()
        self.commit(blocked=True, code="FILE_READ")

    def test_quoted_interpreter_path_can_be_removed_with_original_path(self):
        interpreter = self.root / ".git/python's executable"
        interpreter.symlink_to(sys.executable)
        self.manage("install", executable=interpreter)
        self.assertEqual(self.hook.read_bytes(), hooks.launcher(str(interpreter)))
        self.changed_safe_file()
        self.commit()
        interpreter.unlink()
        self.write("safe.txt", b"yet another ordinary line\n")
        self.git("add", "--", "safe.txt")
        self.commit(blocked=True, code="HOOK_ABORTED")
        self.manage("uninstall", expected=2)
        self.assertEqual(self.manage("uninstall", "--installed-python", str(interpreter))["status"], "absent")

    def test_install_without_dependencies_is_refused_without_hook(self):
        (self.here / ".deps").unlink()
        self.assertEqual(self.manage("install", expected=2)["code"], "HOOK_RUNTIME")
        self.assertFalse(self.hook.exists())

    def test_existing_executable_and_nonexecutable_hooks_are_preserved(self):
        self.hook.parent.mkdir(exist_ok=True)
        original = b"#!/bin/sh\n# existing public user hook\nexit 0\n"
        for mode in (0o600, 0o700):
            with self.subTest(mode=mode):
                self.hook.write_bytes(original)
                self.hook.chmod(mode)
                before = unchanged_metadata(self.hook)
                self.manage("install", expected=2)
                self.manage("uninstall", expected=2)
                self.assertEqual(self.hook.read_bytes(), original)
                self.assertEqual(unchanged_metadata(self.hook), before)

    def test_hook_and_hooks_directory_symlinks_are_preserved(self):
        self.hook.parent.mkdir(exist_ok=True)
        target = self.write(".git/foreign-hook", b"public existing hook\n")
        self.hook.symlink_to(target)
        self.manage("install", expected=2)
        self.assertTrue(self.hook.is_symlink())
        self.hook.unlink()
        self.hook.parent.rmdir()
        directory = self.root / ".git/foreign-hooks"
        directory.mkdir()
        self.hook.parent.symlink_to(directory, target_is_directory=True)
        self.manage("install", expected=2)
        self.assertTrue(self.hook.parent.is_symlink())
        self.assertEqual(list(directory.iterdir()), [])

    def test_effective_local_global_empty_and_environment_hooks_paths_are_preserved(self):
        config = self.root / ".git/config"
        self.git("config", "--local", "core.hooksPath", "public-hooks")
        before = config.read_bytes()
        self.assertEqual(self.manage("install", expected=2)["code"], "HOOKS_PATH_CONFIGURED")
        self.assertEqual(config.read_bytes(), before)
        self.git("config", "--local", "--unset", "core.hooksPath")
        global_config = self.write(".git/public-global-config", b'[core]\n hooksPath = public-hooks\n')
        env = dict(os.environ, GIT_CONFIG_GLOBAL=str(global_config))
        before = config.read_bytes(), global_config.read_bytes()
        self.assertEqual(self.manage("install", env=env, expected=2)["code"], "HOOKS_PATH_CONFIGURED")
        self.assertEqual((config.read_bytes(), global_config.read_bytes()), before)
        self.git("config", "--local", "core.hooksPath", "")
        self.assertEqual(self.manage("install", expected=2)["code"], "HOOKS_PATH_CONFIGURED")
        self.git("config", "--local", "--unset", "core.hooksPath")
        env = dict(os.environ, GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.hooksPath",
                   GIT_CONFIG_VALUE_0="public-hooks")
        self.assertEqual(self.manage("install", env=env, expected=2)["code"], "HOOKS_PATH_CONFIGURED")
        self.assertFalse(self.hook.exists())

    def test_install_and_uninstall_are_idempotent_and_preserve_other_hooks_and_config(self):
        other = self.write(".git/hooks/commit-msg", b"#!/bin/sh\nexit 0\n")
        config = (self.root / ".git/config").read_bytes()
        self.assertEqual(self.manage("status")["status"], "absent")
        self.install()
        before = self.hook.read_bytes(), unchanged_metadata(self.hook)
        self.install()
        self.assertEqual((self.hook.read_bytes(), unchanged_metadata(self.hook)), before)
        self.assertEqual(self.manage("status")["status"], "installed")
        self.assertEqual(self.manage("uninstall")["status"], "absent")
        self.assertEqual(self.manage("uninstall")["status"], "absent")
        self.assertEqual(other.read_bytes(), b"#!/bin/sh\nexit 0\n")
        self.assertEqual((self.root / ".git/config").read_bytes(), config)

    def test_modified_owned_hook_is_not_overwritten_or_deleted(self):
        self.install()
        changed = self.hook.read_bytes() + b"# public user change\n"
        self.hook.write_bytes(changed)
        for action in ("install", "status", "uninstall"):
            self.assertEqual(self.manage(action, expected=2)["code"], "HOOK_CONFLICT")
            self.assertEqual(self.hook.read_bytes(), changed)

    def test_nonexecutable_owned_hook_is_not_reported_as_installed(self):
        self.install()
        self.hook.chmod(0o600)
        for action in ("status", "install"):
            self.assertEqual(self.manage(action, expected=2)["code"], "HOOK_NOT_EXECUTABLE")
        self.assertEqual(self.manage("uninstall")["status"], "absent")

    def test_separate_git_directory_and_git_directory_symlink_are_rejected(self):
        actual = self.root / ".git"
        moved = self.root / ".git-saved"
        actual.rename(moved)
        actual.write_text("gitdir: .git-saved\n")
        self.assertEqual(self.manage("install", expected=2)["code"], "GIT_LAYOUT")
        actual.unlink()
        actual.symlink_to(moved, target_is_directory=True)
        self.assertEqual(self.manage("install", expected=2)["code"], "GIT_LAYOUT")
        actual.unlink()
        moved.rename(actual)

    def test_foreign_git_environment_is_rejected(self):
        foreign = Path(self.temp.name) / "foreign"
        foreign.mkdir()
        result = self.command(["git", "-c", "init.templateDir=", "init", "-q"], cwd=foreign)
        self.assertEqual(result.returncode, 0, "temporary foreign Git setup failed")
        env = dict(os.environ, GIT_DIR=str(foreign / ".git"))
        self.assertEqual(self.manage("install", env=env, expected=2)["code"], "GIT_LAYOUT")
        self.assertFalse(self.hook.exists())
        self.assertFalse((foreign / ".git/hooks/pre-commit").exists())

    def test_concurrent_hook_creation_is_not_overwritten(self):
        original_link = os.link
        def concurrent_link(source, destination, **options):
            self.write(".git/hooks/pre-commit", b"public concurrent hook\n")
            return original_link(source, destination, **options)
        with patch.object(hooks.os, "link", side_effect=concurrent_link):
            with self.assertRaises(FileExistsError):
                hooks.manage("install", root=self.root)
        self.assertEqual(self.hook.read_bytes(), b"public concurrent hook\n")
        self.assertEqual([p.name for p in self.hook.parent.iterdir()], ["pre-commit"])

    def test_concurrent_hook_change_during_uninstall_is_preserved(self):
        self.install()
        original_reader = hooks.read_hook
        def concurrent_read(directory):
            result = original_reader(directory)
            self.hook.write_bytes(result[0] + b"# concurrent public change\n")
            return result
        with patch.object(hooks, "read_hook", side_effect=concurrent_read):
            with self.assertRaises(hooks.HookFailure) as error:
                hooks.manage("uninstall", root=self.root)
        self.assertEqual(error.exception.code, "HOOK_CHANGED")
        self.assertTrue(self.hook.read_bytes().endswith(b"# concurrent public change\n"))

    def test_repeat_install_rechecks_hook_after_runtime_validation(self):
        self.install()
        def replace_during_ready(root):
            self.hook.write_bytes(b"public concurrent replacement\n")
        with patch.object(hooks, "ready", side_effect=replace_during_ready):
            with self.assertRaises(hooks.HookFailure) as error:
                hooks.manage("install", root=self.root)
        self.assertEqual(error.exception.code, "HOOK_CONFLICT")
        self.assertEqual(self.hook.read_bytes(), b"public concurrent replacement\n")

    def test_repeat_install_rechecks_effective_configuration(self):
        self.install()
        def configure_during_ready(root):
            self.git("config", "--local", "core.hooksPath", "public-hooks")
        with patch.object(hooks, "ready", side_effect=configure_during_ready):
            with self.assertRaises(hooks.HookFailure) as error:
                hooks.manage("install", root=self.root)
        self.assertEqual(error.exception.code, "HOOKS_PATH_CONFIGURED")

    def test_restrictive_umask_still_installs_executable_hook(self):
        self.hook.parent.mkdir(exist_ok=True)
        previous = os.umask(0o777)
        try:
            self.install()
        finally:
            os.umask(previous)
        self.assertTrue(self.hook.stat().st_mode & 0o100, "Git would ignore a nonexecutable hook")
        self.changed_safe_file()
        self.commit()

    def test_source_parent_directory_links_are_rejected_before_runtime(self):
        for name in ("tests/secret_scan", "tests"):
            with self.subTest(parent=name):
                source = self.root / name
                target = Path(self.temp.name) / "public-source"
                source.rename(target)
                source.symlink_to(target, target_is_directory=True)
                try:
                    with self.assertRaises(hooks.HookFailure) as error:
                        hooks.manage("install", root=self.root)
                    self.assertEqual(error.exception.code, "HOOK_ENTRY")
                    self.assertTrue(source.is_symlink())
                    self.assertFalse(self.hook.exists())
                finally:
                    source.unlink()
                    target.rename(source)
                    if self.hook.exists():
                        self.hook.unlink()

    def test_repeat_install_repairs_hook_removed_during_runtime_validation(self):
        self.install()
        expected = self.hook.read_bytes()
        with patch.object(hooks, "ready", side_effect=lambda root: self.hook.unlink()):
            self.assertEqual(hooks.manage("install", root=self.root)["status"], "installed")
        self.assertTrue(self.hook.is_file(), "install reported success without a hook")
        self.assertEqual(self.hook.read_bytes(), expected)

    def test_import_output_and_zero_system_exit_are_contained(self):
        self.install()
        self.changed_safe_file()
        marker = "public-import-output"
        self.write("tests/secret_scan/backend.py",
                   ("import sys\nprint(" + repr(marker) + ")\n"
                    "print(" + repr(marker) + ", file=sys.stderr)\nraise SystemExit(0)\n").encode())
        self.commit(blocked=True, code="HOOK_SCAN_FAILED", forbidden=(marker.encode(),))

    def test_invalid_cli_arguments_do_not_echo_values(self):
        result = self.manage("invalid-" + TOKEN.decode(), expected=2)
        self.assertEqual(result["code"], "USAGE")


if __name__ == "__main__":
    unittest.main()
