import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';
import 'package:keex_forui_candidate/src/app.dart';

/// 按逻辑像素设好屏幕和系统字号再起应用。字号 2.0 就是系统设置里的 200%。
Future<void> pumpApp(
  WidgetTester tester, {
  Size size = const Size(390, 844),
  double textScale = 1,
  Brightness brightness = Brightness.dark,
}) async {
  tester.view.physicalSize = size * 3;
  tester.view.devicePixelRatio = 3;
  tester.platformDispatcher.textScaleFactorTestValue = textScale;
  addTearDown(tester.view.reset);
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
  await tester.pumpWidget(KeexForuiApp(brightness: brightness));
  await tester.pumpAndSettle();
}

Future<void> openFirstEntry(WidgetTester tester) async {
  await tester.tap(find.byType(FTile).first);
  await tester.pumpAndSettle();
}

Finder editableIn(Finder field) => find.descendant(of: field, matching: find.byType(EditableText));

/// 读屏树里所有能被念出来的文字：标签、值、提示、提示框。
List<String> spokenTexts(WidgetTester tester) {
  final texts = <String>[];
  void visit(SemanticsNode node) {
    final data = node.getSemanticsData();
    texts.addAll([data.label, data.value, data.hint, data.tooltip].whereType<String>().where((t) => t.isNotEmpty));
    node.visitChildren((child) {
      visit(child);
      return true;
    });
  }

  for (final view in tester.binding.renderViews) {
    final root = view.owner?.semanticsOwner?.rootSemanticsNode;
    if (root != null) visit(root);
  }
  return texts;
}

/// 读屏树里所有输入框节点的标签。
List<String> textFieldLabels(WidgetTester tester) {
  final labels = <String>[];
  void visit(SemanticsNode node) {
    final data = node.getSemanticsData();
    if (data.flagsCollection.isTextField) labels.add(data.label);
    node.visitChildren((child) {
      visit(child);
      return true;
    });
  }

  for (final view in tester.binding.renderViews) {
    final root = view.owner?.semanticsOwner?.rootSemanticsNode;
    if (root != null) visit(root);
  }
  return labels;
}

/// 收集布局溢出等框架报错而不是遇到第一个就停，方便一次看全哪些组件撑不住大字。
Future<List<String>> collectFlutterErrors(Future<void> Function() body) async {
  final errors = <String>[];
  final previous = FlutterError.onError;
  FlutterError.onError = (details) => errors.add(details.exceptionAsString().split('\n').first);
  try {
    await body();
  } finally {
    FlutterError.onError = previous;
  }
  return errors;
}
