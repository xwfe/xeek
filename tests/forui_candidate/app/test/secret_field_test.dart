// 秘密字段发给系统的配置和读屏树内容。Flutter 把 setClient 的参数原样交给 Android/iOS 的输入法桥，
// 所以这里断言的 JSON 就是系统输入法和自动填充服务看到的东西。
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';
import 'package:keex_forui_candidate/src/secret_field.dart';
import 'package:keex_forui_candidate/src/synthetic.dart';

import 'helpers.dart';

const entry = SyntheticEntry(0);

Future<Map<String, dynamic>> focus(WidgetTester tester, Finder editable) async {
  await tester.ensureVisible(editable);
  await tester.pumpAndSettle();
  await tester.showKeyboard(editable);
  return tester.testTextInput.setClientArgs!;
}

void main() {
  testWidgets('keex 秘密框：不报给自动填充，不让输入法学习，不联想不纠错', (tester) async {
    await pumpApp(tester);
    await openFirstEntry(tester);
    final args = await focus(tester, editableIn(find.byType(KeexSecretField)));
    expect(args['obscureText'], isTrue);
    expect(args['autocorrect'], isFalse);
    expect(args['enableSuggestions'], isFalse);
    expect(args['enableIMEPersonalizedLearning'], isFalse);
    expect(args['autofill'], isNull, reason: 'autofill 为 null 才是关掉自动填充');
    expect((args['inputType'] as Map<String, dynamic>)['name'], 'TextInputType.text');
  });

  testWidgets('forui 自带密码框的默认值：报给自动填充，允许输入法学习，显示按钮 40×40（变了要重新评估）', (tester) async {
    await pumpApp(tester);
    await tester.tap(find.byIcon(FLucideIcons.settings));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('forui 自带密码框'), 300, scrollable: find.byType(Scrollable).last);
    await tester.tap(find.text('forui 自带密码框'));
    await tester.pumpAndSettle();
    final args = await focus(tester, find.byType(EditableText));
    expect(args['obscureText'], isTrue);
    expect(args['autocorrect'], isFalse);
    expect(args['enableSuggestions'], isFalse);
    expect(args['enableIMEPersonalizedLearning'], isTrue);
    final autofill = args['autofill'] as Map<String, dynamic>;
    expect(autofill['hints'], [AutofillHints.password]);
    expect(tester.getSize(find.byType(FButton)), const Size(40, 40));
  });

  testWidgets('密码和动态口令默认不进读屏树，用户点了显示才有', (tester) async {
    final handle = tester.ensureSemantics();
    await pumpApp(tester);
    await openFirstEntry(tester);
    final otp = '${entry.otp.substring(0, 3)} ${entry.otp.substring(3)}';

    var spoken = spokenTexts(tester);
    expect(spoken.where((t) => t.contains(entry.hiddenValue)), isEmpty);
    expect(spoken.where((t) => t.contains(entry.otp) || t.contains(otp)), isEmpty);
    expect(spoken, contains('动态口令，已隐藏'));

    await tester.tap(find.bySemanticsLabel('显示密码'));
    await tester.tap(find.bySemanticsLabel('显示动态口令'));
    await tester.pumpAndSettle();
    spoken = spokenTexts(tester);
    expect(spoken.where((t) => t.contains(entry.hiddenValue)), isNotEmpty);
    expect(spoken, contains(otp));
    handle.dispose();
  });
}
