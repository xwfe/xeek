// K070：kdbx.dart 编译到浏览器后能不能真的读改写。只用于对照，不进产品。
import 'dart:js_interop';
import 'dart:typed_data';

import 'package:kdbx/kdbx.dart';

@JS('keexDartProbe')
external set _probe(JSFunction value);

Future<String> run(Uint8List data, String password) async {
  final clock = Stopwatch()..start();
  final format = KdbxFormat();
  final file = await format.read(data, Credentials(ProtectedValue.fromString(password)));
  final opened = clock.elapsedMilliseconds;
  final saved = await file.save();
  return 'opened ${opened}ms, saved ${clock.elapsedMilliseconds - opened}ms, ${saved.length} bytes';
}

void main() {
  _probe = ((JSUint8Array data, JSString password) => run(data.toDart, password.toDart)
      .then((value) => value.toJS)
      .catchError((Object error) => 'failed: $error'.toJS)
      .toJS).toJS;
}
