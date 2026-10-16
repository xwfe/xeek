"""keex 的 KDBX 测试对照工具：只读解码、语义规范化与比较。

只用于合成样本和候选库的无损测试（K002/K003），不是 keex 的生产实现，
也不会写出 KDBX 文件。真实密码库不要交给它，见 adr/REAL_DATA_RULES.md。
"""

from .reader import (
    DecodedKdbx,
    KdbxError,
    KdbxFormatError,
    KdbxIntegrityError,
    KdbxKeyError,
    KdbxUnsupported,
    read_kdbx,
    read_plain_xml,
)

__all__ = [
    "DecodedKdbx",
    "KdbxError",
    "KdbxFormatError",
    "KdbxIntegrityError",
    "KdbxKeyError",
    "KdbxUnsupported",
    "read_kdbx",
    "read_plain_xml",
]
