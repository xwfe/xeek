// K070：kpasslib 的原生读改写 helper，参数和 keex-history-edit 相同，便于用同一套核对。
//
//   dart run bin/helper.dart 输入 输出 条目UUID 新用户名   （口令从 stdin 读一行）
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:kpasslib/kpasslib.dart';

Future<void> main(List<String> args) async {
  final password = stdin.readLineSync(encoding: utf8) ?? '';
  final data = Uint8List.fromList(File(args[0]).readAsBytesSync());
  try {
    final db = await KdbxDatabase.fromBytes(
      data: data,
      credentials: KdbxCredentials(password: ProtectedData.fromString(password)),
    );
    final target = args[2].replaceAll('-', '').toLowerCase();
    final entry = db.root.allEntries.firstWhere((e) => _hex(e.uuid) == target);
    entry.pushHistory();
    entry.fields['UserName'] = KdbxTextField.fromText(text: args[3]);
    File(args[1]).writeAsBytesSync(await db.save());
  } catch (error) {
    stderr.writeln('$error');
    exit(1);
  }
}

String _hex(KdbxUuid uuid) => uuid.bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
