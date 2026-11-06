import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

import 'detail_page.dart';
import 'synthetic.dart';

class PasswordsPage extends StatefulWidget {
  const PasswordsPage({super.key});

  @override
  State<PasswordsPage> createState() => _PasswordsPageState();
}

class _PasswordsPageState extends State<PasswordsPage> {
  String query = '';

  @override
  Widget build(BuildContext context) {
    final results = query.isEmpty ? syntheticEntries : syntheticEntries.where((e) => e.matches(query)).toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        FTextField(
          label: const Text('搜索'),
          hint: '标题或账号',
          textInputAction: TextInputAction.search,
          control: FTextFieldControl.managed(onChange: _onSearch),
        ),
        const SizedBox(height: 8),
        // 测试靠这一行判断：拼音还没上屏时列表不能先按字母过滤。
        Text('共 ${results.length} 条', style: context.theme.typography.body.sm),
        const SizedBox(height: 8),
        Expanded(
          child: ListView.builder(
            itemCount: results.length,
            itemBuilder: (context, i) => _EntryTile(entry: results[i]),
          ),
        ),
      ],
    );
  }

  void _onSearch(TextEditingValue value) {
    // 输入法组合中（比如打“mima”还没选字）不过滤，否则列表会按拼音字母先闪一遍。
    if (value.composing.isValid && !value.composing.isCollapsed) return;
    if (value.text != query) setState(() => query = value.text);
  }
}

class _EntryTile extends StatelessWidget {
  const _EntryTile({required this.entry});

  final SyntheticEntry entry;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    // forui 的列表项默认把文字截成一行加省略号。基线要求大字时换行，所以在这里显式写换行参数覆盖它。
    child: FTile(
      prefix: const Icon(FLucideIcons.keyRound),
      title: Text(entry.title, softWrap: true, overflow: TextOverflow.visible),
      subtitle: Text('${entry.kind.label} · ${entry.account}', softWrap: true, overflow: TextOverflow.visible),
      suffix: entry.favorite ? const Icon(FLucideIcons.star, semanticLabel: '已收藏') : null,
      onPress: () => Navigator.of(context).push(adaptiveRoute(DetailPage(entry: entry))),
    ),
  );
}
