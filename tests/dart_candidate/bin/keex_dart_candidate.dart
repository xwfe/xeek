// 仅用于公开合成库的 K003 对照实验：读取 → 改一个 UserName → 保存为新文件。
// 不是生产 writer；只打印计数或稳定错误码，不输出字段值。
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:kdbx/kdbx.dart';

const _maxInputBytes = 64 * 1024 * 1024;

class _Failure implements Exception {
  _Failure(this.code);
  final String code;
}

Future<String> _readPassword() async {
  final bytes = <int>[];
  await for (final chunk in stdin) {
    bytes.addAll(chunk);
    if (bytes.length > 4096) {
      throw _Failure('password_too_long');
    }
  }
  String password;
  try {
    password = utf8.decode(bytes);
  } on FormatException {
    throw _Failure('invalid_password_input');
  }
  if (password.endsWith('\n')) {
    password = password.substring(0, password.length - 1);
    if (password.endsWith('\r')) {
      password = password.substring(0, password.length - 1);
    }
  }
  if (password.isEmpty || password.contains('\n') || password.contains('\r')) {
    throw _Failure('invalid_password_input');
  }
  return password;
}

KdbxUuid _uuidFromHex(String hex) {
  if (!RegExp(r'^[0-9a-f]{32}$').hasMatch(hex)) {
    throw _Failure('invalid_uuid');
  }
  final bytes = Uint8List(16);
  for (var i = 0; i < 16; i++) {
    bytes[i] = int.parse(hex.substring(i * 2, i * 2 + 2), radix: 16);
  }
  return KdbxUuid.fromBytes(bytes);
}

Uint8List _readLimited(String path, String code) {
  final file = File(path);
  if (!file.existsSync() || file.lengthSync() > _maxInputBytes) {
    throw _Failure(code);
  }
  return file.readAsBytesSync();
}

int _historyCount(KdbxFile file) => file.body.rootGroup.getAllEntries().fold(
  0,
  (sum, entry) => sum + entry.history.length,
);

Future<Map<String, Object>> _run(List<String> args) async {
  if (args.length != 4 && args.length != 5) {
    throw _Failure('invalid_arguments');
  }
  final input = args[0], output = args[1], newUsername = args[3];
  if (File(input).absolute.path == File(output).absolute.path) {
    throw _Failure('output_equals_input');
  }
  if (newUsername.isEmpty || newUsername.length > 4096) {
    throw _Failure('invalid_new_username');
  }
  final target = _uuidFromHex(args[2]);
  final keyFile = args.length == 5
      ? _readLimited(args[4], 'keyfile_open_failed')
      : null;
  final password = await _readPassword();
  final source = _readLimited(input, 'input_open_failed');

  // 不传 Argon2 实现时，kdbx 2.5.0 使用 pointycastle 纯 Dart Argon2，不加载包里附带的原生库。
  final format = KdbxFormat();
  final KdbxFile file;
  try {
    file = await format.read(
      source,
      Credentials.composite(ProtectedValue.fromString(password), keyFile),
    );
  } on KdbxInvalidKeyException {
    throw _Failure('invalid_credentials');
  } catch (_) {
    // 不支持的 KDF/外层密码会抛 Exception 或 pointycastle 的 ArgumentError，统一归为打开失败。
    throw _Failure('database_open_failed');
  }

  final root = file.body.rootGroup;
  final entries = root.getAllEntries().length;
  final groups = root.getAllGroups().length;
  final attachments = file.ctx.binariesIterable.length;
  final historyBefore = _historyCount(file);
  final matches = root.getAllEntries().where((e) => e.uuid == target).toList();
  if (matches.length != 1) {
    throw _Failure('entry_not_found');
  }
  final entry = matches.single;
  final current = entry.getString(KdbxKeyCommon.USER_NAME);
  if (current == null) {
    throw _Failure('username_field_missing');
  }
  if (current.getText() == newUsername) {
    throw _Failure('username_is_unchanged');
  }
  // 保留原保护标记；setString 在修改前自动把旧状态追加到历史末尾。
  entry.setString(
    KdbxKeyCommon.USER_NAME,
    current is ProtectedValue
        ? ProtectedValue.fromString(newUsername)
        : PlainValue(newUsername),
  );
  final historyAfter = _historyCount(file);
  if (root.getAllEntries().length != entries ||
      root.getAllGroups().length != groups ||
      file.ctx.binariesIterable.length != attachments ||
      historyAfter != historyBefore + 1) {
    throw _Failure('model_count_mismatch');
  }

  final Uint8List ciphertext;
  try {
    ciphertext = await file.save();
  } on Exception {
    throw _Failure('database_save_failed');
  }

  // 加密完成后才排他创建新目标；已有文件一律拒绝，不覆盖。
  final destination = File(output);
  try {
    destination.createSync(exclusive: true);
  } on FileSystemException {
    throw _Failure('output_create_failed');
  }
  final handle = destination.openSync(mode: FileMode.writeOnly);
  try {
    handle.writeFromSync(ciphertext);
    handle.flushSync();
  } on FileSystemException {
    throw _Failure('output_write_failed');
  } finally {
    handle.closeSync();
  }
  return {
    'ok': true,
    'version': file.header.version.toString(),
    'entries': entries,
    'groups': groups,
    'attachments': attachments,
    'history_before': historyBefore,
    'history_after': historyAfter,
    'bytes': ciphertext.length,
  };
}

Future<void> main(List<String> args) async {
  try {
    stdout.writeln(jsonEncode(await _run(args)));
  } on _Failure catch (failure) {
    stderr.writeln(jsonEncode({'ok': false, 'error': failure.code}));
    exitCode = 1;
  } catch (_) {
    // 库内部错误的原文可能带字段内容，只报固定码。
    stderr.writeln(jsonEncode({'ok': false, 'error': 'library_error'}));
    exitCode = 1;
  }
}
