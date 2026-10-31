// Web 实现：KDF 和解析都在 Worker 里，和纯 JS 探针用的是同一个 kdbx-worker.js 和同一个 WASM。
import 'dart:async';
import 'dart:js_interop';
import 'dart:js_interop_unsafe';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

import 'vault_core.dart';

extension type _Reply._(JSObject _) implements JSObject {
  external bool? get ready;
  external int? get id;
  external bool? get ok;
  external JSAny? get value;
  external String? get message;
  external bool? get trapped;
}

class PlatformVaultCore implements VaultCore {
  web.Worker? _worker;
  Future<void>? _ready;
  int _next = 0;
  final _pending = <int, Completer<_Reply>>{};

  Future<void> _start() {
    return _ready ??= () {
      final ready = Completer<void>();
      final worker = web.Worker('kdbx-worker.js'.toJS, web.WorkerOptions(type: 'module'));
      worker.onmessage = ((web.MessageEvent event) {
        final reply = event.data as _Reply;
        if (reply.ready == true) {
          ready.complete();
          return;
        }
        _pending.remove(reply.id)?.complete(reply);
      }).toJS;
      worker.onerror = ((web.Event _) {
        if (!ready.isCompleted) ready.completeError(VaultError('Worker 加载失败', instanceLost: true));
      }).toJS;
      _worker = worker;
      return ready.future;
    }();
  }

  Future<JSAny?> _call(String op, JSObject args, [JSObject? transfer]) async {
    await _start();
    final id = _next += 1;
    final completer = Completer<_Reply>();
    _pending[id] = completer;
    final message = JSObject()
      ..setProperty('id'.toJS, id.toJS)
      ..setProperty('op'.toJS, op.toJS)
      ..setProperty('args'.toJS, args);
    if (transfer != null) {
      _worker!.postMessage(message, [transfer].toJS);
    } else {
      _worker!.postMessage(message);
    }
    final reply = await completer.future;
    if (reply.ok != true) {
      final lost = reply.trapped == true;
      if (lost) await close();
      throw VaultError(reply.message ?? 'unknown', instanceLost: lost);
    }
    return reply.value;
  }

  @override
  Future<Map<String, dynamic>> open(Uint8List bytes, String password) async {
    // 传过去之后这边的缓冲区就不能用了，所以先复制一份。
    final buffer = Uint8List.fromList(bytes).buffer.toJS;
    final args = JSObject()
      ..setProperty('bytes'.toJS, buffer)
      ..setProperty('password'.toJS, password.toJS);
    final summary = await _call('open', args, buffer);
    return (summary.dartify() as Map).cast<String, dynamic>();
  }

  @override
  Future<void> setUsername(String entry, String username) async {
    await _call('setUsername', JSObject()
      ..setProperty('entry'.toJS, entry.toJS)
      ..setProperty('username'.toJS, username.toJS));
  }

  @override
  Future<Uint8List> save(String password) async {
    final value = await _call('save', JSObject()..setProperty('password'.toJS, password.toJS));
    return (value as JSArrayBuffer).toDart.asUint8List();
  }

  @override
  Future<void> close() async {
    _worker?.terminate();
    _worker = null;
    _ready = null;
    for (final pending in _pending.values) {
      pending.completeError(VaultError('已关闭', instanceLost: true));
    }
    _pending.clear();
  }
}
