"""Salsa20/20 密钥流，只用来还原 KDBX 3.1 的受保护字段。

cryptography 库没有 Salsa20，而 KDBX 3.1 的内层保护流只用它，所以这里按
Bernstein 的规范自写。它只在测试里解开已有数据，不加密任何新数据；
正确性由规范里的测试向量和 KeePassXC 生成的 3.1 样本共同核对。
"""

from __future__ import annotations

import struct

_MASK = 0xFFFFFFFF
_SIGMA = (0x61707865, 0x3320646E, 0x79622D32, 0x6B206574)  # "expand 32-byte k"


def _rotl(value: int, count: int) -> int:
    return ((value << count) & _MASK) | (value >> (32 - count))


def _quarter(x: list[int], a: int, b: int, c: int, d: int) -> None:
    x[b] ^= _rotl((x[a] + x[d]) & _MASK, 7)
    x[c] ^= _rotl((x[b] + x[a]) & _MASK, 9)
    x[d] ^= _rotl((x[c] + x[b]) & _MASK, 13)
    x[a] ^= _rotl((x[d] + x[c]) & _MASK, 18)


def salsa20_core(state: list[int]) -> bytes:
    """对 16 个 32 位字做 20 轮（10 次列轮 + 行轮），输出 64 字节。"""
    x = list(state)
    for _ in range(10):
        _quarter(x, 0, 4, 8, 12)
        _quarter(x, 5, 9, 13, 1)
        _quarter(x, 10, 14, 2, 6)
        _quarter(x, 15, 3, 7, 11)
        _quarter(x, 0, 1, 2, 3)
        _quarter(x, 5, 6, 7, 4)
        _quarter(x, 10, 11, 8, 9)
        _quarter(x, 15, 12, 13, 14)
    return struct.pack("<16I", *((x[i] + state[i]) & _MASK for i in range(16)))


class Salsa20:
    """256 位密钥、64 位 nonce、计数器从 0 开始；按顺序吐出密钥流。"""

    def __init__(self, key: bytes, nonce: bytes) -> None:
        if len(key) != 32 or len(nonce) != 8:
            raise ValueError("Salsa20 需要 32 字节密钥和 8 字节 nonce")
        k = struct.unpack("<8I", key)
        n = struct.unpack("<2I", nonce)
        self._state = [
            _SIGMA[0], k[0], k[1], k[2], k[3], _SIGMA[1], n[0], n[1],
            0, 0, _SIGMA[2], k[4], k[5], k[6], k[7], _SIGMA[3],
        ]
        self._buffer = b""

    def keystream(self, length: int) -> bytes:
        out = bytearray()
        while len(out) < length:
            if not self._buffer:
                self._buffer = salsa20_core(self._state)
                counter = (self._state[8] | (self._state[9] << 32)) + 1
                self._state[8] = counter & _MASK
                self._state[9] = (counter >> 32) & _MASK
            take = min(length - len(out), len(self._buffer))
            out += self._buffer[:take]
            self._buffer = self._buffer[take:]
        return bytes(out)
