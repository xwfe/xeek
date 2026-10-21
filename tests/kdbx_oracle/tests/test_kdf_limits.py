"""Argon2 原语已知答案，以及在本机原生派生/解压前拒绝恶意参数。"""
from __future__ import annotations

import gzip
import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from kdbx_oracle import reader, KdbxFormatError, KdbxIntegrityError, KdbxUnsupported

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "kdbx"
sys.path.insert(0, str(FIXTURES))
import mutate

COMPOSITE = bytes(range(32))
FORMATS = {0x04: "<I", 0x05: "<Q", 0x08: "<?", 0x0C: "<i", 0x0D: "<q"}


def parameters(identifier=reader.KDF_ARGON2ID):
    return {
        "$UUID": (0x42, identifier.bytes), "S": (0x42, b"synthetic-salt"),
        "P": (0x04, 1), "M": (0x05, 8192), "I": (0x05, 1), "V": (0x04, 19),
    }


def encoded(params):
    items = []
    for key, (kind, value) in params.items():
        raw = struct.pack(FORMATS[kind], value) if kind in FORMATS else (
            value.encode("utf-8") if kind == 0x18 else value)
        items.append((kind, key, raw))
    return mutate.variant_dictionary(items)


class Argon2LimitsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = (FIXTURES / "upstream_kdbxweb" / "Argon2id.kdbx").read_bytes()
        cls.keyfile = (FIXTURES / "upstream_kdbxweb" / "demo.key").read_bytes()
        if reader._argon2_backend is None:
            raise AssertionError("Argon2d acceptance requires the registered dependency")

    def changed_header(self, params):
        header = mutate.build_header(self.original, {reader.H_KDF: encoded(params)})
        return mutate.v4_assemble(self.original, header)

    def assert_before_native(self, params, error, reason=None):
        # 重算无密钥 SHA-256、保留已失效 HMAC，确保触及参数入口。
        data = self.changed_header(params)
        with patch.object(reader, "Argon2id") as native_id, patch.object(
            reader._argon2_backend, "hash_secret_raw"
        ) as native_d:
            context = self.assertRaisesRegex(error, reason) if reason else self.assertRaises(error)
            with context:
                reader.read_kdbx(data, "demo", self.keyfile)
            native_id.assert_not_called()
            native_d.assert_not_called()

    def test_argon2d_version16_published_cli_vector(self):
        # 官方 16.0.0 测试（含 8 个尾随 NUL 的盐），不是本次生成的期望。
        # https://github.com/hynek/argon2-cffi/blob/1112a2e58336e549f8efb7f2d747f5249f85f6be/tests/test_low_level.py
        params = parameters(reader.KDF_ARGON2D)
        params.update({"S": (0x42, b"somesalt" + b"\0" * 8), "P": (0x04, 4),
                       "M": (0x05, 65536 * 1024), "I": (0x05, 2), "V": (0x04, 0x10)})
        self.assertEqual(reader._argon2d(b"password", params).hex(),
                         "9ca3b9fc007d09daf489dcf854e9a785ff5a32c62ec50acf26477977add23225")

    def test_argon2d_version19_published_cli_vector(self):
        # https://github.com/hynek/argon2-cffi/blob/1fcae4fc1b7ff192b5ade54f6616771e5cf5f391/tests/test_low_level.py
        params = parameters(reader.KDF_ARGON2D)
        params.update({"S": (0x42, b"somesalt"), "P": (0x04, 4),
                       "M": (0x05, 65536 * 1024), "I": (0x05, 2)})
        self.assertEqual(reader._argon2d(b"password", params).hex(),
                         "7199f977eac587e65fb91866da21941a072b5b960b78ceaaecbdef06c766140d")

    def test_argon2id_existing_backend_matches_published_cli_vector(self):
        # 同一官方 25.1.0 测试文件还给出 Argon2id 向量，核对现有独立后端。
        params = parameters()
        params.update({"S": (0x42, b"somesalt"), "P": (0x04, 4),
                       "M": (0x05, 65536 * 1024), "I": (0x05, 2)})
        self.assertEqual(reader._argon2id(b"password", params).hex(),
                         "1a9677b0afe81fda7b548895e7a1bfeb8668ffc19a530e37e088a668fab1c02a")

    def test_each_budget_is_rejected_before_native_call(self):
        changes = [
            {"M": (0x05, reader.MAX_ARGON2_MEMORY + 1)},
            {"I": (0x05, reader.MAX_ARGON2_ITERATIONS + 1)},
            {"P": (0x04, reader.MAX_ARGON2_PARALLELISM + 1), "M": (0x05, 1 << 20)},
            # 单项均在范围内，但总工作量 512 MiB * 5 超过 2 GiB-pass。
            {"M": (0x05, 512 << 20), "I": (0x05, 5)},
        ]
        for identifier in (reader.KDF_ARGON2D, reader.KDF_ARGON2ID):
            for change in changes:
                with self.subTest(kdf=str(identifier), fields=list(change)):
                    params = parameters(identifier)
                    params.update(change)
                    self.assert_before_native(params, KdbxUnsupported, "Argon2 参数")

    def test_oversized_salt_secret_and_associated_data_are_bounded(self):
        for key in ("S", "K", "A"):
            with self.subTest(key=key):
                params = parameters()
                params[key] = (0x42, b"x" * (reader.MAX_ARGON2_INPUT_BYTES + 1))
                self.assert_before_native(params, KdbxUnsupported, "Argon2 参数")

    def test_invalid_zero_values_and_memory_per_lane_are_rejected(self):
        for identifier in (reader.KDF_ARGON2D, reader.KDF_ARGON2ID):
            for change in ({"I": (0x05, 0)}, {"P": (0x04, 0)}, {"M": (0x05, 0)},
                           {"P": (0x04, 2), "M": (0x05, 8192)}, {"S": (0x42, b"short")}):
                with self.subTest(kdf=str(identifier), fields=list(change)):
                    params = parameters(identifier)
                    params.update(change)
                    self.assert_before_native(params, KdbxFormatError)

    def test_boolean_signed_and_wrong_width_integers_are_not_coerced(self):
        changes = [
            {"I": (0x08, True)}, {"M": (0x08, True)}, {"P": (0x08, True)},
            {"P": (0x0C, -1)}, {"I": (0x0D, -1)}, {"M": (0x0D, -1)},
            {"P": (0x05, 1)}, {"I": (0x04, 1)}, {"M": (0x04, 8192)}, {"V": (0x05, 19)},
        ]
        for identifier in (reader.KDF_ARGON2D, reader.KDF_ARGON2ID):
            for change in changes:
                with self.subTest(kdf=str(identifier), change=change):
                    params = parameters(identifier)
                    params.update(change)
                    self.assert_before_native(params, KdbxFormatError)

    def test_all_required_fields_and_uuid_length_are_checked(self):
        for key in parameters():
            params = parameters()
            del params[key]
            with self.subTest(missing=key):
                self.assert_before_native(params, KdbxFormatError)
        for length in (0, 15, 17):
            params = parameters()
            params["$UUID"] = (0x42, bytes(length))
            self.assert_before_native(params, KdbxFormatError, "UUID")

    def test_byte_fields_and_optional_fields_reject_wrong_types(self):
        for identifier in (reader.KDF_ARGON2D, reader.KDF_ARGON2ID):
            for key in ("S", "K", "A", "$UUID"):
                params = parameters(identifier)
                params[key] = (0x18, "synthetic")
                with self.subTest(kdf=str(identifier), key=key):
                    self.assert_before_native(params, KdbxFormatError)

    def test_unknown_versions_are_not_delegated_to_backend(self):
        for identifier, versions in ((reader.KDF_ARGON2D, (0, 17, 18, 20)),
                                     (reader.KDF_ARGON2ID, (0, 16, 20))):
            for version in versions:
                params = parameters(identifier)
                params["V"] = (0x04, version)
                self.assert_before_native(params, KdbxUnsupported, "Argon2 版本")

    def test_argon2d_nonempty_k_or_a_is_explicitly_unsupported(self):
        for key in ("K", "A"):
            params = parameters(reader.KDF_ARGON2D)
            params[key] = (0x42, b"synthetic-extra")
            self.assert_before_native(params, KdbxUnsupported, "K/A")

    def test_argon2id_preserves_optional_secret_and_associated_data(self):
        params = parameters()
        params.update({"K": (0x42, b"synthetic-key"), "A": (0x42, b"synthetic-context")})
        with patch.object(reader, "Argon2id") as native:
            reader._argon2id(COMPOSITE, params)
            self.assertEqual(native.call_args.kwargs["secret"], b"synthetic-key")
            self.assertEqual(native.call_args.kwargs["ad"], b"synthetic-context")
            native.return_value.derive.assert_called_once_with(COMPOSITE)

    def test_memory_conversion_floors_kib_without_changing_reported_bytes(self):
        for identifier in (reader.KDF_ARGON2D, reader.KDF_ARGON2ID):
            params = parameters(identifier)
            params.update({"M": (0x05, 8192 + 1023), "K": (0x42, b""), "A": (0x42, b"")})
            with patch.object(reader, "Argon2id") as native_id, patch.object(
                reader._argon2_backend, "hash_secret_raw", return_value=COMPOSITE
            ) as native_d:
                _, info = reader._derive_transformed_key(4, {reader.H_KDF: encoded(params)}, COMPOSITE)
                chosen = native_d if identifier == reader.KDF_ARGON2D else native_id
                self.assertEqual(chosen.call_args.kwargs["memory_cost"], 8)
                self.assertEqual(info["memory"], 9215)
                if identifier == reader.KDF_ARGON2D:
                    self.assertEqual(native_d.call_args.kwargs["secret"], COMPOSITE)
                    self.assertEqual(native_d.call_args.kwargs["version"], 19)

    def test_bad_header_sha_precedes_kdf_even_when_parameters_are_huge(self):
        params = parameters()
        params["M"] = (0x05, 1 << 40)
        data = bytearray(self.changed_header(params))
        _, _, _, header_end = reader._parse_outer_header(data)
        data[header_end] ^= 1
        with patch.object(reader, "Argon2id") as native_id, patch.object(
            reader._argon2_backend, "hash_secret_raw"
        ) as native_d:
            with self.assertRaisesRegex(KdbxIntegrityError, "SHA-256"):
                reader.read_kdbx(bytes(data), "demo", self.keyfile)
            native_id.assert_not_called()
            native_d.assert_not_called()

    def test_missing_argon2_dependency_is_explicit_and_existing_id_still_works(self):
        with patch.object(reader, "_argon2_backend", None):
            with self.assertRaisesRegex(KdbxUnsupported, "argon2-cffi"):
                reader._argon2d(COMPOSITE, parameters(reader.KDF_ARGON2D))
            opened = reader.read_kdbx(self.original, "demo", self.keyfile)
            self.assertEqual(opened.kdf["name"], "argon2id")

    def test_native_hashing_failure_has_a_controlled_error(self):
        with patch.object(reader._argon2_backend, "hash_secret_raw",
                          side_effect=reader._Argon2HashingError("synthetic native failure")):
            with self.assertRaisesRegex(KdbxUnsupported, "后端"):
                reader._argon2d(COMPOSITE, parameters(reader.KDF_ARGON2D))


class VariantDictionaryLimitsTest(unittest.TestCase):
    def test_every_truncated_prefix_has_a_format_error(self):
        data = encoded(parameters())
        for size in range(len(data)):
            with self.subTest(size=size), self.assertRaises(KdbxFormatError):
                reader.parse_variant_dictionary(data[:size])

    def test_negative_and_oversized_lengths_are_rejected(self):
        for length in (-1, 0x7FFFFFFF):
            for data in (
                b"\x00\x01\x42" + struct.pack("<i", length),
                b"\x00\x01\x42\x01\x00\x00\x00S" + struct.pack("<i", length),
            ):
                with self.subTest(length=length), self.assertRaises(KdbxFormatError):
                    reader.parse_variant_dictionary(data)

    def test_invalid_utf8_key_or_text_is_a_format_error(self):
        data = b"\x00\x01\x42\x01\x00\x00\x00\xff\x00\x00\x00\x00\x00"
        with self.assertRaises(KdbxFormatError):
            reader.parse_variant_dictionary(data)
        with self.assertRaises(KdbxFormatError):
            reader.parse_variant_dictionary(mutate.variant_dictionary([(0x18, "S", b"\xff")]))

    def test_duplicate_keys_are_not_silently_overwritten(self):
        for key in ("$UUID", "M", "unknown"):
            data = mutate.variant_dictionary([(0x42, key, b"a"), (0x42, key, b"b")])
            with self.assertRaisesRegex(KdbxFormatError, "重复"):
                reader.parse_variant_dictionary(data)

    def test_trailing_data_and_wrong_numeric_lengths_are_rejected(self):
        for data in (encoded(parameters()) + b"\x00", encoded(parameters()) + b"tail",
                     mutate.variant_dictionary([(0x04, "P", b"\x01")])):
            with self.assertRaises(KdbxFormatError):
                reader.parse_variant_dictionary(data)

    def test_known_types_roundtrip_and_minor_version_remains_informational(self):
        params = parameters()
        params.update({"text": (0x18, "合成"), "signed": (0x0C, -7), "flag": (0x08, True)})
        data = encoded(params)
        self.assertEqual(reader.parse_variant_dictionary(data), params)
        self.assertEqual(reader.parse_variant_dictionary(b"\xff\x01" + data[2:]), params)
        with self.assertRaises(KdbxUnsupported):
            reader.parse_variant_dictionary(b"\x00\x02" + data[2:])


class XmlBudgetConfigurationTest(unittest.TestCase):
    def test_invalid_public_xml_limits_are_rejected_before_processing(self):
        for limit in (-1, 0, True, None, "10", 1.5, reader.MAX_XML_BYTES + 1):
            with self.subTest(limit=limit), patch.object(reader, "_parse_outer_header") as parser:
                with self.assertRaises(ValueError):
                    reader.read_kdbx(b"", "synthetic", max_xml_bytes=limit)
                parser.assert_not_called()

    def test_invalid_gzip_limits_never_construct_a_decompressor(self):
        for limit in (-1, 0, True, None, "10", 1.5, reader.MAX_XML_BYTES + 1):
            with self.subTest(limit=limit), patch.object(reader.zlib, "decompressobj") as native:
                with self.assertRaises(ValueError):
                    reader._gunzip(b"", limit)
                native.assert_not_called()
        self.assertEqual(reader._gunzip(gzip.compress(b"x"), 1), b"x")


if __name__ == "__main__":
    unittest.main()
