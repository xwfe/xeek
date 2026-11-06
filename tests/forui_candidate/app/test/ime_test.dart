// 中文输入法的组合态：打拼音时文字带着 composing 区间，选字上屏后区间才消失。
// 这里模拟的是输入法发给 Flutter 的编辑状态，真机输入法另在模拟器和浏览器里测。
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

TextEditingValue composing(String text) => TextEditingValue(
  text: text,
  selection: TextSelection.collapsed(offset: text.length),
  composing: TextRange(start: 0, end: text.length),
);

TextEditingValue committed(String text) =>
    TextEditingValue(text: text, selection: TextSelection.collapsed(offset: text.length));

void main() {
  testWidgets('搜索框：拼音组合中不过滤，上屏后才过滤；forui 不抹掉组合区间', (tester) async {
    await pumpApp(tester);
    final search = find.byType(EditableText).first;
    await tester.showKeyboard(search);

    tester.testTextInput.updateEditingValue(composing('shi'));
    await tester.pump();
    expect(tester.widget<EditableText>(search).controller.value.composing, const TextRange(start: 0, end: 3));
    expect(find.text('共 10000 条'), findsOneWidget);

    tester.testTextInput.updateEditingValue(composing('shili'));
    await tester.pump();
    expect(find.text('共 10000 条'), findsOneWidget);

    tester.testTextInput.updateEditingValue(committed('示例'));
    await tester.pump();
    expect(tester.widget<EditableText>(search).controller.text, '示例');
    // 10 个合成站名里只有“示例银行”含“示例”。
    expect(find.text('共 1000 条'), findsOneWidget);
  });

  testWidgets('详情页标题框：在已有文字后面接着打拼音，上屏后原文不丢', (tester) async {
    await pumpApp(tester);
    await openFirstEntry(tester);
    final title = find.byType(EditableText).first;
    await tester.showKeyboard(title);
    final before = tester.widget<EditableText>(title).controller.text;

    tester.testTextInput.updateEditingValue(
      TextEditingValue(
        text: '${before}zhanghu',
        selection: TextSelection.collapsed(offset: before.length + 7),
        composing: TextRange(start: before.length, end: before.length + 7),
      ),
    );
    await tester.pump();
    tester.testTextInput.updateEditingValue(committed('$before账户'));
    await tester.pump();
    expect(tester.widget<EditableText>(title).controller.text, '$before账户');
  });
}
