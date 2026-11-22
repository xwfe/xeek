"""生成器的拒绝覆盖与清单失败路径；只写自动清理的合成临时目录。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "kdbx"
sys.path.insert(0, str(FIXTURES))
import matrix_generate as generator
import matrix_source as source


class MatrixGenerationGuardTest(unittest.TestCase):
    def test_existing_output_is_not_overwritten(self):
        case = source.cases()[0]
        with tempfile.TemporaryDirectory(prefix="keex-matrix-guard-") as directory:
            root = Path(directory)
            target = root / source.filename(case, "import")
            target.write_bytes(b"public synthetic original")
            with patch.object(generator, "HERE", root), patch.object(source, "build") as build:
                with self.assertRaises(FileExistsError):
                    generator.generate_one(case, "unused")
                build.assert_not_called()
            self.assertEqual(target.read_bytes(), b"public synthetic original")

    def test_manifest_failure_leaves_unregistered_files_and_retry_refuses_them(self):
        case = source.cases()[0]
        with tempfile.TemporaryDirectory(prefix="keex-matrix-guard-") as directory:
            root = Path(directory)
            for name in generator.PROVENANCE:
                (root / name).write_text("public synthetic source")
            def fake_generate(_case, _binary):
                stages = []
                for stage in case["stages"]:
                    path = root / source.filename(case, stage)
                    path.write_bytes(b"public synthetic fixture placeholder")
                    stages.append({"file": path.name})
                return {"id": case["id"], "stages": stages}
            with patch.object(generator, "HERE", root), patch.object(generator, "MANIFEST", root / "matrix_manifest.json"), \
                    patch.object(sys, "argv", ["matrix_generate.py", "--only", case["id"]]), \
                    patch.object(generator.shutil, "which", return_value="synthetic-cli"), \
                    patch.object(generator.generate, "keepassxc_version", return_value="2.7.12"), \
                    patch.object(generator, "generate_one", side_effect=fake_generate) as create, \
                    patch.object(generator, "save_manifest", side_effect=OSError("synthetic manifest failure")):
                with self.assertRaises(OSError):
                    generator.main()
                self.assertFalse((root / ".matrix-generate.lock").exists())
                self.assertFalse((root / "matrix_manifest.json").exists())
                self.assertEqual(len(list(root.glob("*.kdbx"))), 3)
                with self.assertRaises(FileExistsError):
                    generator.main()
                self.assertEqual(create.call_count, 1)

    def test_fixed_provenance_preserves_generation_snapshot_after_documentation_correction(self):
        manifest = json.loads((FIXTURES / "matrix_manifest.json").read_text())
        old, current = manifest["generation_provenance"], manifest["provenance"]
        self.assertEqual([name for name in old if old[name] != current[name]], ["source.py", "matrix_generate.py"])
        # source.py 的修订只固定 gzip 头部 OS 字节；源 XML 摘要由 test_matrix 逐项复核。
        revision, = manifest["verification_revisions"]
        self.assertEqual((revision["file"], revision["previous_sha256"], revision["sha256"]),
                         ("source.py", old["source.py"], current["source.py"]))
        self.assertEqual(old["matrix_generate.py"], "944325e891345f86ebecc85c314f374364fb397dd79fdcc87ff16270ba535761")
        self.assertIn("no executable statements", manifest["analysis_note"])


if __name__ == "__main__":
    unittest.main()

