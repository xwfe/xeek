import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

import 'transport.dart';

class PlatformTransport implements Transport {
  @override
  Future<String> text(String path) async => (await (await web.window.fetch(path.toJS).toDart).text().toDart).toDart;

  @override
  Future<Uint8List> bytes(String path) async =>
      (await (await web.window.fetch(path.toJS).toDart).arrayBuffer().toDart).toDart.asUint8List();

  @override
  Future<void> post(String path, Object body, {String? contentType}) async {
    final payload = body is Uint8List ? body.toJS as JSAny : (body as String).toJS;
    await web.window.fetch(path.toJS, web.RequestInit(
      method: 'POST',
      headers: {'Content-Type': contentType ?? 'application/octet-stream'}.jsify()! as JSObject,
      body: payload,
    )).toDart;
  }
}
