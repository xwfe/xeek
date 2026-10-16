"""语义规范化与比较的单元测试：直接用手写 XML，不经过加解密。"""

import base64
import struct
import unittest
import xml.etree.ElementTree as ET

from kdbx_oracle.reader import DecodedKdbx
from kdbx_oracle.semantic import canonicalize, diff, normalize_time, summarize

GROUP = base64.b64encode(bytes(range(16))).decode()
ENTRY_A = base64.b64encode(bytes([1] * 16)).decode()
ENTRY_B = base64.b64encode(bytes([2] * 16)).decode()


def decoded(xml: str, binaries=None, version=(4, 1)) -> DecodedKdbx:
    return DecodedKdbx(
        major=version[0], minor=version[1], cipher="aes256-cbc", kdf={}, compressed=True,
        inner_stream="chacha20", header_hash="not-applicable", root=ET.fromstring(xml),
        binaries=binaries or {},
    )


def entry(uuid: str, password: str = "pw", extra: str = "") -> str:
    return (
        f"<Entry><UUID>{uuid}</UUID>"
        f"<String><Key>Title</Key><Value>t</Value></String>"
        f"<String><Key>Password</Key><Value Protected=\"True\">{password}</Value></String>"
        f"{extra}</Entry>"
    )


def database(*entries: str, meta: str = "") -> str:
    return (
        f"<KeePassFile><Meta><Generator>x</Generator>{meta}</Meta><Root><Group><UUID>{GROUP}</UUID>"
        f"{''.join(entries)}</Group></Root></KeePassFile>"
    )


class NormalizeTimeTest(unittest.TestCase):
    def test_kdbx4_base64_matches_iso(self):
        seconds = 63_900_000_000  # 2025 年前后
        encoded = base64.b64encode(struct.pack("<q", seconds)).decode()
        iso = normalize_time(encoded)
        self.assertRegex(iso, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual(normalize_time(iso), iso)

    def test_epoch_zero_is_year_one(self):
        self.assertEqual(normalize_time(base64.b64encode(bytes(8)).decode()), "0001-01-01T00:00:00Z")

    def test_garbage_is_left_alone(self):
        self.assertEqual(normalize_time("not a time"), "not a time")


class DiffTest(unittest.TestCase):
    def test_field_order_and_bool_case_do_not_matter(self):
        a = database(entry(ENTRY_A), meta="<RecycleBinEnabled>True</RecycleBinEnabled>")
        b_entry = (
            f"<Entry><UUID>{ENTRY_A}</UUID>"
            "<String><Key>Password</Key><Value Protected=\"True\">pw</Value></String>"
            "<String><Key>Title</Key><Value>t</Value></String></Entry>"
        )
        b = database(b_entry, meta="<RecycleBinEnabled>true</RecycleBinEnabled>")
        self.assertEqual(diff(canonicalize(decoded(a)), canonicalize(decoded(b))), [])

    def test_bool_case_inside_user_value_does_matter(self):
        a = database(entry(ENTRY_A, extra="<String><Key>X</Key><Value>true</Value></String>"))
        b = database(entry(ENTRY_A, extra="<String><Key>X</Key><Value>True</Value></String>"))
        self.assertEqual(len(diff(canonicalize(decoded(a)), canonicalize(decoded(b)))), 1)

    def test_protected_value_is_redacted_by_default(self):
        a = canonicalize(decoded(database(entry(ENTRY_A, "old-secret"))))
        b = canonicalize(decoded(database(entry(ENTRY_A, "new-secret!"))))
        (only,) = diff(a, b)
        self.assertNotIn("secret", str(only))
        self.assertIn("10 字符", only.detail)
        self.assertIn("new-secret!", str(diff(a, b, reveal=True)[0]))

    def test_losing_protection_flag_is_reported(self):
        a = database(entry(ENTRY_A))
        b = a.replace(' Protected="True"', "")
        (only,) = diff(canonicalize(decoded(a)), canonicalize(decoded(b)))
        self.assertIn("保护标记", only.detail)

    def test_entry_order_is_reported(self):
        a = database(entry(ENTRY_A), entry(ENTRY_B))
        b = database(entry(ENTRY_B), entry(ENTRY_A))
        kinds = [d.kind for d in diff(canonicalize(decoded(a)), canonicalize(decoded(b)))]
        self.assertEqual(kinds, ["order"])

    def test_unknown_element_is_reported_when_dropped(self):
        a = database(entry(ENTRY_A, extra="<FutureThing a=\"1\">x</FutureThing>"))
        b = database(entry(ENTRY_A))
        (only,) = diff(canonicalize(decoded(a)), canonicalize(decoded(b)))
        self.assertEqual(only.kind, "removed")
        self.assertTrue(only.path.endswith("/FutureThing"))
        self.assertIn("KeePassFile/Root/Group/Entry/FutureThing", summarize(decoded(a))["unknown_elements"])

    def test_binary_compared_by_content_not_pool_index(self):
        ref = "<Binary><Key>a.txt</Key><Value Ref=\"{}\"/></Binary>"
        a = decoded(database(entry(ENTRY_A, extra=ref.format(0))), {"0": (b"x", False), "1": (b"y", False)})
        b = decoded(database(entry(ENTRY_A, extra=ref.format(1))), {"0": (b"y", False), "1": (b"x", False)})
        self.assertEqual(diff(canonicalize(a), canonicalize(b)), [])
        c = decoded(database(entry(ENTRY_A, extra=ref.format(0))), {"0": (b"z", False)})
        self.assertEqual(len(diff(canonicalize(a), canonicalize(c))), 1)

    def test_tag_order_and_separator_do_not_matter(self):
        a = database(entry(ENTRY_A, extra="<Tags>合成;web</Tags>"))
        b = database(entry(ENTRY_A, extra="<Tags>web,合成</Tags>"))
        self.assertEqual(diff(canonicalize(decoded(a)), canonicalize(decoded(b))), [])

    def test_empty_element_equals_missing_element(self):
        a = database(entry(ENTRY_A))
        b = database(entry(ENTRY_A, extra=(
            "<Tags/><ForegroundColor/><History/>"
            "<String><Key>Notes</Key><Value/></String>"
            "<String><Key>URL</Key><Value Protected=\"True\"></Value></String>"
        )))
        self.assertEqual(diff(canonicalize(decoded(a)), canonicalize(decoded(b))), [])

    def test_empty_unknown_element_still_counts(self):
        # 不认识的空元素可能是新版本或插件的开关标记，丢了必须报。
        a = database(entry(ENTRY_A, extra="<FutureFlag/>"), meta="<PluginFlag/>")
        b = database(entry(ENTRY_A))
        removed = sorted(d.path.rsplit("/", 1)[1] for d in diff(canonicalize(decoded(a)), canonicalize(decoded(b))))
        self.assertEqual(removed, ["FutureFlag", "PluginFlag"])

    def test_attachment_protection_reported_apart_from_content(self):
        ref = "<Binary><Key>a.txt</Key><Value Ref=\"0\"/></Binary>"
        a = decoded(database(entry(ENTRY_A, extra=ref)), {"0": (b"x", False)})
        b = decoded(database(entry(ENTRY_A, extra=ref)), {"0": (b"x", True)})
        (only,) = diff(canonicalize(a), canonicalize(b))
        self.assertEqual(only.aspect, "attrs")
        self.assertIn("sha256:", str(diff(canonicalize(a), canonicalize(decoded(
            database(entry(ENTRY_A, extra=ref)), {"0": (b"y", True)})))[0]))

    def test_empty_custom_field_still_counts(self):
        a = database(entry(ENTRY_A))
        b = database(entry(ENTRY_A, extra="<String><Key>X-Empty</Key><Value/></String>"))
        (only,) = diff(canonicalize(decoded(a)), canonicalize(decoded(b)))
        self.assertEqual((only.kind, only.path.rsplit("/", 1)[1]), ("added", "String=X-Empty"))

    def test_ignore_pattern(self):
        a = canonicalize(decoded(database(entry(ENTRY_A))))
        b = canonicalize(decoded(database(entry(ENTRY_A)).replace("<Generator>x", "<Generator>y")))
        self.assertEqual(len(diff(a, b)), 1)
        self.assertEqual(diff(a, b, ignore=["*/Meta/Generator"]), [])

    def test_history_entries_keyed_by_position(self):
        history = "<History>{}</History>".format(entry(ENTRY_A, "h1") + entry(ENTRY_A, "h2"))
        a = canonicalize(decoded(database(entry(ENTRY_A, extra=history))))
        labels = [label for label, _ in dict(dict(a.children)["Root"].children)["Group=" + bytes(range(16)).hex()].children]
        self.assertIn("Entry=" + bytes([1] * 16).hex(), labels)
        entry_node = dict(dict(dict(a.children)["Root"].children)["Group=" + bytes(range(16)).hex()].children)[
            "Entry=" + bytes([1] * 16).hex()
        ]
        history_labels = [label for label, _ in dict(entry_node.children)["History"].children]
        self.assertEqual(history_labels, ["Entry", "Entry#1"])


if __name__ == "__main__":
    unittest.main()
