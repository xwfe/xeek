"""Salsa20 自写实现的向量测试。端到端正确性另由 test_fixtures 里的 KDBX 3.1 样本保证。"""

import struct
import unittest

from kdbx_oracle.salsa20 import Salsa20, salsa20_core


class Salsa20Test(unittest.TestCase):
    def test_spec_expansion_example(self):
        # Bernstein《Salsa20 specification》第 9 节：k0=1..16，k1=201..216，n=101..116。
        k0 = bytes(range(1, 17))
        k1 = bytes(range(201, 217))
        n = bytes(range(101, 117))
        sigma = b"expa", b"nd 3", b"2-by", b"te k"
        words = (
            sigma[0] + k0 + sigma[1] + n + sigma[2] + k1 + sigma[3]
        )
        state = list(struct.unpack("<16I", words))
        expected = bytes([
            69, 37, 68, 39, 41, 15, 107, 193, 255, 139, 122, 6, 170, 233, 217, 98,
            89, 144, 182, 106, 21, 51, 200, 65, 239, 49, 222, 34, 215, 114, 40, 126,
            104, 197, 7, 225, 197, 153, 31, 2, 102, 78, 76, 176, 84, 245, 246, 184,
            177, 160, 133, 130, 6, 72, 149, 119, 192, 195, 132, 236, 234, 103, 246, 74,
        ])
        self.assertEqual(salsa20_core(state), expected)

    def test_estream_set1_vector0(self):
        # eSTREAM Salsa20/20 256 位密钥 Set 1 vector 0：key=80 00..00，IV 全零。
        stream = Salsa20(b"\x80" + bytes(31), bytes(8))
        expected = bytes.fromhex(
            "E3BE8FDD8BECA2E3EA8EF9475B29A6E7003951E1097A5C38D23B7A5FAD9F6844"
            "B22C97559E2723C7CBBD3FE4FC8D9A0744652A83E72A9C461876AF4D7EF1A117"
        )
        self.assertEqual(stream.keystream(64), expected)

    def test_split_reads_match_single_read(self):
        key = bytes(range(32))
        nonce = bytes(range(8))
        whole = Salsa20(key, nonce).keystream(200)
        pieces = Salsa20(key, nonce)
        joined = b"".join(pieces.keystream(n) for n in (1, 63, 64, 5, 67))
        self.assertEqual(joined, whole)


if __name__ == "__main__":
    unittest.main()
