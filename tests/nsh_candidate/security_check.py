"""检查 Rust 私有哨兵边界；TSX 输入 trace 负控制必须被观测到。"""
from __future__ import annotations

import argparse
import json
import re
import unittest
from pathlib import Path

PRIVATE = "SYNTHETIC-K092-PRIVATE-BOUNDARY"
NEGATIVE = "SYNTHETIC-K092-INPUT-NEGATIVE"
HERE = Path(__file__).resolve().parent


def verify_trace(text):
    if not text.strip():
        raise ValueError("EMPTY_TRACE")
    if PRIVATE in text:
        raise ValueError("PRIVATE_SENTINEL_EXPOSED")
    if NEGATIVE not in text:
        raise ValueError("NEGATIVE_CONTROL_MISSING")
    if not re.search(r'^ +Text \{ id: \d+, text: "FIELD_NOT_FOUND",', text, re.M) or "剪贴板 owned" not in text:
        raise ValueError("PROTECTED_PATH_NOT_OBSERVED")
    if not re.search(r"✓ \d+ tests: \d+ passed, 0 failed", text):
        raise ValueError("INCOMPLETE_TEST_RUN")


class BoundaryTests(unittest.TestCase):
    def test_normal(self):
        verify_trace(NEGATIVE + '\n   Text { id: 1, text: "FIELD_NOT_FOUND", content: 1x1 }\n剪贴板 owned\n✓ 20 tests: 20 passed, 0 failed')

    def test_empty_and_unreached(self):
        for text in ("", "unrelated output", NEGATIVE):
            with self.assertRaises(ValueError):
                verify_trace(text)

    def test_private_exposure_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "PRIVATE_SENTINEL_EXPOSED"):
            verify_trace(PRIVATE + NEGATIVE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BoundaryTests))
    if not result.wasSuccessful():
        return 1
    try:
        verify_trace(args.trace.read_text())
        outputs = HERE / "rust/target/outputs"
        receipts = list(outputs.rglob("*.json"))
        if any(not (outputs / f"receipt-{sample}.json").is_file()
               for sample in ("baseline", "scale-1000", "scale-10000")):
            raise ValueError("MISSING_RECEIPTS")
        for receipt in receipts:
            text = receipt.read_text()
            if PRIVATE in text or NEGATIVE in text:
                raise ValueError("RUNTIME_METADATA_EXPOSED")
    except (OSError, ValueError):
        print("K092 boundary audit: FAIL (trace or runtime metadata)")
        return 1
    print(json.dumps({"private_trace": "absent", "tsx_trace_negative_control": "observed",
                      "runtime_metadata_files": len(receipts), "status": "pass"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
