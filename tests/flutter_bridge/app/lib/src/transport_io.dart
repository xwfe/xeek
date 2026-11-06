import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'transport.dart';

class PlatformTransport implements Transport {
  static const _server = 'http://127.0.0.1:47120';
  final _client = HttpClient();

  Future<Uint8List> _read(HttpClientResponse response) async {
    final builder = BytesBuilder(copy: false);
    await for (final chunk in response) {
      builder.add(chunk);
    }
    return builder.takeBytes();
  }

  @override
  Future<String> text(String path) async => utf8.decode(await bytes(path));

  @override
  Future<Uint8List> bytes(String path) async => _read(await (await _client.getUrl(Uri.parse('$_server$path'))).close());

  @override
  Future<void> post(String path, Object body, {String? contentType}) async {
    final request = await _client.postUrl(Uri.parse('$_server$path'));
    if (contentType != null) request.headers.contentType = ContentType.parse(contentType);
    request.add(body is Uint8List ? body : utf8.encode(body as String));
    await _read(await request.close());
  }
}
