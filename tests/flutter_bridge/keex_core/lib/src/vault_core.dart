import 'dart:typed_data';

import 'unsupported.dart'
    if (dart.library.js_interop) 'web.dart'
    if (dart.library.ffi) 'native.dart';

/// 一个已解锁的库。KDF 不会占用调用方线程：原生在后台 isolate，Web 在 Worker。
///
/// 锁库就是 [close]：Web 上直接结束 Worker，WASM 线性内存不能缩小也不能保证清零，只有丢弃整个实例才算数。
abstract class VaultCore {
  factory VaultCore() = PlatformVaultCore;

  /// 解锁并返回摘要（不含字段值）。密码错误等可恢复的错误抛 [VaultError]。
  Future<Map<String, dynamic>> open(Uint8List bytes, String password);

  Future<void> setUsername(String entry, String username);

  Future<Uint8List> save(String password);

  Future<void> close();
}

class VaultError implements Exception {
  VaultError(this.message, {this.instanceLost = false});

  final String message;

  /// 核心崩了（比如 Argon2 内存超出能力）：这个实例不能再用，要新建一个。
  final bool instanceLost;

  @override
  String toString() => 'VaultError: $message';
}
