// K070：kpasslib 编译到浏览器后能不能真的读写。
import 'dart:js_interop';
import 'dart:typed_data';

import 'package:kpasslib/kpasslib.dart';

@JS('keexDartProbe')
external set _probe(JSFunction value);

Future<String> run(Uint8List data, String password) async {
  final clock = Stopwatch()..start();
  final db = await KdbxDatabase.fromBytes(
    data: data,
    credentials: KdbxCredentials(password: ProtectedData.fromString(password)),
  );
  final opened = clock.elapsedMilliseconds;
  final saved = await db.save();
  return 'opened ${opened}ms, saved ${clock.elapsedMilliseconds - opened}ms, ${saved.length} bytes';
}

void main() {
  _probe = ((JSUint8Array data, JSString password) => run(data.toDart, password.toDart)
      .then((value) => value.toJS)
      .catchError((Object error) => 'failed: $error'.toJS)
      .toJS).toJS;
}
