// K070：走 Dart 接口 → FFI → Rust 的完整路径，参数和别的候选 helper 相同，用同一把尺子量。
import 'dart:convert';
import 'dart:io';

import 'package:keex_core/keex_core.dart';

Future<void> main(List<String> args) async {
  final password = stdin.readLineSync(encoding: utf8) ?? '';
  final core = VaultCore();
  try {
    await core.open(File(args[0]).readAsBytesSync(), password);
    await core.setUsername(args[2], args[3]);
    File(args[1]).writeAsBytesSync(await core.save(password));
    await core.close();
  } on VaultError catch (error) {
    stderr.writeln(error.message);
    exitCode = 1;
  }
}
