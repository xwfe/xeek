// 原生实现：直接 dart:ffi。生产里动态库由 build hook 或 cargokit 打包，这里用环境变量指路径。
import 'dart:convert';
import 'dart:ffi';
import 'dart:io';
import 'dart:isolate';
import 'dart:typed_data';

import 'package:ffi/ffi.dart';

import 'vault_core.dart';

typedef _Handle = Pointer<Void>;

DynamicLibrary _open() => DynamicLibrary.open(Platform.environment['KEEX_CORE_LIB'] ?? 'libkeex_wasm_core.dylib');

final _lib = _open();
final _lastError = _lib.lookupFunction<Pointer<Utf8> Function(), Pointer<Utf8> Function()>('keex_last_error');
final _openVault = _lib.lookupFunction<
    Int32 Function(Pointer<Uint8>, Size, Pointer<Utf8>, Pointer<_Handle>),
    int Function(Pointer<Uint8>, int, Pointer<Utf8>, Pointer<_Handle>)>('keex_vault_open');
final _summary = _lib.lookupFunction<Pointer<Utf8> Function(_Handle), Pointer<Utf8> Function(_Handle)>('keex_vault_summary');
final _setUsername = _lib.lookupFunction<
    Int32 Function(_Handle, Pointer<Utf8>, Pointer<Utf8>),
    int Function(_Handle, Pointer<Utf8>, Pointer<Utf8>)>('keex_vault_set_username');
final _save = _lib.lookupFunction<
    Int32 Function(_Handle, Pointer<Utf8>, Pointer<Pointer<Uint8>>, Pointer<Size>),
    int Function(_Handle, Pointer<Utf8>, Pointer<Pointer<Uint8>>, Pointer<Size>)>('keex_vault_save');
final _bytesFree = _lib.lookupFunction<Void Function(Pointer<Uint8>, Size), void Function(Pointer<Uint8>, int)>('keex_bytes_free');
final _stringFree = _lib.lookupFunction<Void Function(Pointer<Utf8>), void Function(Pointer<Utf8>)>('keex_string_free');
final _vaultFree = _lib.lookupFunction<Void Function(_Handle), void Function(_Handle)>('keex_vault_free');

/// 错误信息属于调用线程，所以和失败的调用在同一个 isolate 里取。
Never _throwLastError() => throw VaultError(_lastError().toDartString());

int _openInIsolate(Uint8List bytes, String password) {
  return using((arena) {
    final data = arena<Uint8>(bytes.length);
    data.asTypedList(bytes.length).setAll(0, bytes);
    final out = arena<_Handle>();
    if (_openVault(data, bytes.length, password.toNativeUtf8(allocator: arena), out) != 0) _throwLastError();
    return out.value.address;
  });
}

Uint8List _saveInIsolate(int address, String password) {
  return using((arena) {
    final out = arena<Pointer<Uint8>>();
    final length = arena<Size>();
    if (_save(_Handle.fromAddress(address), password.toNativeUtf8(allocator: arena), out, length) != 0) _throwLastError();
    final copy = Uint8List.fromList(out.value.asTypedList(length.value));
    _bytesFree(out.value, length.value);
    return copy;
  });
}

class PlatformVaultCore implements VaultCore {
  _Handle? _vault;

  @override
  Future<Map<String, dynamic>> open(Uint8List bytes, String password) async {
    await close();
    final address = await Isolate.run(() => _openInIsolate(bytes, password));
    _vault = _Handle.fromAddress(address);
    final text = _summary(_vault!);
    final summary = jsonDecode(text.toDartString()) as Map<String, dynamic>;
    _stringFree(text);
    return summary;
  }

  @override
  Future<void> setUsername(String entry, String username) async {
    using((arena) {
      if (_setUsername(_vault!, entry.toNativeUtf8(allocator: arena), username.toNativeUtf8(allocator: arena)) != 0) {
        _throwLastError();
      }
    });
  }

  @override
  Future<Uint8List> save(String password) {
    final address = _vault!.address;
    return Isolate.run(() => _saveInIsolate(address, password));
  }

  @override
  Future<void> close() async {
    final vault = _vault;
    _vault = null;
    if (vault != null) _vaultFree(vault);
  }
}
