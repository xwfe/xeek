import 'label_io.dart' if (dart.library.js_interop) 'label_web.dart';

/// 这一轮探针的标签；没有就不跑。
String? autoLabel() => platformLabel();
