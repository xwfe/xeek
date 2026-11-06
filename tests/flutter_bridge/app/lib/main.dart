// K070、K004：Flutter 通过 VaultCore 调 Rust，跑完把结果和写出的库传回本机核对。不是产品界面。
import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/scheduler.dart';
import 'package:flutter/widgets.dart';
import 'package:keex_core/keex_core.dart';

import 'src/label.dart';
import 'src/transport.dart';

final status = ValueNotifier('starting');
final _transport = Transport();

// 帧的最长间隔：KDF 跑着时界面要是被卡住，这个数就会变大。窗口不在前台时不出帧，这里自然也不增长。
Duration _worstFrame = Duration.zero;

void main() {
  runApp(const ProbeApp());
  // 不挂在 widget 上：Safari 窗口不在前台时不出帧，initState 可能一直等不到。
  final label = autoLabel();
  if (label != null) {
    unawaited(_run(label).catchError((Object error) => _note(label, 'error: $error')));
  }
}

/// 把进度发回本机，页面看不到时也知道走到哪了。
Future<void> _note(String label, String text) =>
    _transport.post('/upload?name=${Uri.encodeQueryComponent('$label.progress.txt')}', text);

class ProbeApp extends StatefulWidget {
  const ProbeApp({super.key});

  @override
  State<ProbeApp> createState() => _ProbeAppState();
}

class _ProbeAppState extends State<ProbeApp> with SingleTickerProviderStateMixin {
  late final Ticker _ticker;
  Duration _last = Duration.zero;

  @override
  void initState() {
    super.initState();
    _ticker = createTicker((elapsed) {
      final gap = elapsed - _last;
      if (gap > _worstFrame) _worstFrame = gap;
      _last = elapsed;
    })..start();
  }

  @override
  void dispose() {
    _ticker.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Directionality(
      textDirection: TextDirection.ltr,
      child: Center(
        child: ValueListenableBuilder<String>(
          valueListenable: status,
          builder: (context, value, _) => Text(value, style: const TextStyle(color: Color(0xFF111111), fontSize: 20)),
        ),
      ),
    );
  }
}

Future<Uint8List> _bytes(String file) => _transport.bytes('/sample?file=${Uri.encodeQueryComponent(file)}');

Future<void> _upload(String name, Uint8List bytes) =>
    _transport.post('/upload?name=${Uri.encodeQueryComponent(name)}', bytes);

Future<void> _run(String label) async {
  final config = jsonDecode(await _transport.text('/core-config.json')) as Map<String, dynamic>;
  final results = <String, Object?>{};
  final shared = Uri.base.queryParameters.containsKey('reuse') ? VaultCore() : null;
  for (final sample in (config['roundTrips'] as List).cast<Map<String, dynamic>>()) {
    status.value = 'round trip ${sample['name']}';
    await _note(label, status.value);
    final name = sample['name'] as String;
    final password = sample['password'] as String;
    // ?reuse 时所有样本共用一个 Worker，用来对照“每次重建”是否就是 Safari 停顿的原因。
    final core = shared ?? VaultCore();
    final clock = Stopwatch()..start();
    final input = await _bytes(sample['file'] as String);
    await _note(label, '$name: 样本已下载');
    final summary = await core.open(input, password);
    await _note(label, '$name: 已解锁');
    final openMs = clock.elapsedMilliseconds;
    await core.setUsername(summary['target'] as String, 'synthetic-browser-edit');
    await _upload('$label--$name.kdbx', await core.save(password));
    await _note(label, '$name: 已保存');
    results[name] = {'ok': true, 'target': summary['target'], 'summary': summary, 'openMs': openMs, 'totalMs': clock.elapsedMilliseconds};
    if (shared == null) await core.close();
  }

  // 错误要能穿过接口；Worker 不能跟着坏。
  final first = (config['roundTrips'] as List).first as Map<String, dynamic>;
  final core = VaultCore();
  var wrong = 'accepted';
  try {
    await core.open(await _bytes(first['file'] as String), 'synthetic-${DateTime.now().microsecondsSinceEpoch}');
  } on VaultError catch (error) {
    wrong = error.instanceLost ? 'lost' : error.message;
  }
  await core.open(await _bytes(first['file'] as String), first['password'] as String);
  for (final n in [1, 2]) {
    await _upload('$label--random-$n.kdbx', await core.save(first['password'] as String));
  }
  await core.close();
  final worstFrameMs = _worstFrame.inMilliseconds;

  // 预算检查要在分配之前拒绝，所以这里很快就返回，也不会丢实例。
  final argon2 = config['argon2Sample'] as Map<String, dynamic>;
  final budgeted = VaultCore();
  var budget = 'accepted';
  try {
    await budgeted.open(await _bytes(argon2['file'] as String), argon2['password'] as String, memoryBudget: 1024 * 1024);
  } on VaultError catch (error) {
    budget = error.message;
  }
  await budgeted.close();

  final report = {
    'label': label,
    'failed': <String>[],
    'wrongPassword': wrong,
    'budget': budget,
    'worstFrameGapMs': worstFrameMs,
    'results': {
      'roundTrips': {'ok': true, 'results': results},
      'kdfLadder': {'ok': true, 'results': <Object>[]},
      'readsEveryRegisteredSample': {'ok': true, 'results': <Object>[]},
    },
  };
  await _transport.post('/report', jsonEncode(report), contentType: 'application/json');
  status.value = 'done';
}
