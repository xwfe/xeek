import 'dart:typed_data';

import 'vault_core.dart';

class PlatformVaultCore implements VaultCore {
  @override
  Future<Map<String, dynamic>> open(Uint8List bytes, String password, {int memoryBudget = 0}) => throw UnsupportedError('no core on this platform');

  @override
  Future<void> setUsername(String entry, String username) => throw UnsupportedError('no core on this platform');

  @override
  Future<Uint8List> save(String password) => throw UnsupportedError('no core on this platform');

  @override
  Future<void> close() => throw UnsupportedError('no core on this platform');
}
