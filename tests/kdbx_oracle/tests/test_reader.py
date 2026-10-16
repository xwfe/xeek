"""解码器里不依赖样本文件的规则：密钥文件格式判定、XML 编码。"""

import base64
import hashlib
import unittest

from kdbx_oracle import KdbxFormatError, reader

KEY = bytes(range(32))


def xml_keyfile(version: str, data: str, hash_attr: str | None = None) -> bytes:
    attr = f' Hash="{hash_attr}"' if hash_attr is not None else ""
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<KeyFile><Meta><Version>{version}</Version></Meta>'
        f"<Key><Data{attr}>{data}</Data></Key></KeyFile>\n"
    ).encode()


class KeyfileTest(unittest.TestCase):
    """规则按 KeePassXC 2.7.12 src/keys/FileKey.cpp。"""

    def test_raw_32_bytes(self):
        self.assertEqual(reader.keyfile_key(KEY), KEY)

    def test_exact_64_hex(self):
        self.assertEqual(reader.keyfile_key(KEY.hex().encode()), KEY)

    def test_hex_with_whitespace_is_hashed(self):
        # 62 位 hex + \r\n 刚好 64 字节，但不是合法的 hex 密钥文件。
        data = KEY.hex()[:62].encode() + b"\r\n"
        self.assertEqual(len(data), 64)
        self.assertEqual(reader.keyfile_key(data), hashlib.sha256(data).digest())

    def test_xml_v2_with_hash(self):
        digest = hashlib.sha256(KEY).digest()[:4].hex().upper()
        spaced = " ".join(KEY.hex()[i : i + 8] for i in range(0, 64, 8))
        self.assertEqual(reader.keyfile_key(xml_keyfile("2.0", spaced, digest)), KEY)

    def test_xml_v2_missing_hash_rejected(self):
        with self.assertRaises(KdbxFormatError):
            reader.keyfile_key(xml_keyfile("2.0", KEY.hex()))

    def test_xml_v1_base64_with_whitespace(self):
        encoded = base64.b64encode(KEY).decode()
        self.assertEqual(reader.keyfile_key(xml_keyfile("1.0", f"\n  {encoded[:20]}\n  {encoded[20:]}\n")), KEY)

    def test_html_with_doctype_is_hashed_not_rejected(self):
        data = b"<!DOCTYPE html><html><body>synthetic</body></html>"
        self.assertEqual(reader.keyfile_key(data), hashlib.sha256(data).digest())

    def test_other_xml_root_is_hashed(self):
        data = b"<note>synthetic</note>"
        self.assertEqual(reader.keyfile_key(data), hashlib.sha256(data).digest())


class XmlEncodingTest(unittest.TestCase):
    def test_utf16_doctype_rejected(self):
        # UTF-16 的 DOCTYPE 按 UTF-8 字节搜不到，而 expat 会展开它；必须在编码这一关拦下。
        text = (
            '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE KeePassFile [<!ENTITY x "INJECTED">]>'
            "<KeePassFile><Meta><Generator>&x;</Generator></Meta></KeePassFile>"
        )
        with self.assertRaisesRegex(KdbxFormatError, "UTF-8"):
            reader._parse_xml(text.encode("utf-16"))

    def test_declared_latin1_rejected(self):
        with self.assertRaisesRegex(KdbxFormatError, "UTF-8"):
            reader._parse_xml(b'<?xml version="1.0" encoding="ISO-8859-1"?><KeePassFile/>')

    def test_utf8_with_bom_accepted(self):
        root = reader._parse_xml(b'\xef\xbb\xbf<?xml version="1.0" encoding="utf-8"?><KeePassFile/>')
        self.assertEqual(root.tag, "KeePassFile")


if __name__ == "__main__":
    unittest.main()
