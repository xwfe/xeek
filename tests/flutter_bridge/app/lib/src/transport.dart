import 'dart:typed_data';

import 'transport_io.dart' if (dart.library.js_interop) 'transport_web.dart';

/// 探针和本机核对服务之间的通信。Web 同源，手机走 adb reverse。
abstract class Transport {
  factory Transport() = PlatformTransport;

  Future<String> text(String path);

  Future<Uint8List> bytes(String path);

  Future<void> post(String path, Object body, {String? contentType});
}
