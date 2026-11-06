import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

/// 到期日这类日期框。
///
/// forui 的日期框是只读输入框，而 Flutter 的只读输入框不给读屏“点击”动作：
/// Android 上它是能聚焦、不能点击的节点，读屏用户双击打不开日历。
/// 这里把一个点击动作并进同一个读屏节点，打开的仍是 forui 自己的日历弹层。
class KeexDateField extends StatefulWidget {
  const KeexDateField({super.key, required this.label});

  final String label;

  @override
  State<KeexDateField> createState() => _KeexDateFieldState();
}

class _KeexDateFieldState extends State<KeexDateField> {
  bool shown = false;

  @override
  Widget build(BuildContext context) => MergeSemantics(
    child: Semantics(
      onTap: () => setState(() => shown = !shown),
      child: FDateField.calendar(
        label: Text(widget.label),
        popoverControl: FPopoverControl.lifted(shown: shown, onChange: (value) => setState(() => shown = value)),
      ),
    ),
  );
}
