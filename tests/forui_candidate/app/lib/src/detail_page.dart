import 'package:cupertino_ui/cupertino_ui.dart'
    show CupertinoActionSheet, CupertinoActionSheetAction, CupertinoPageRoute, showCupertinoModalPopup;
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';
import 'package:material_ui/material_ui.dart' show ListTile, MaterialPageRoute, showModalBottomSheet;

import 'date_field.dart';
import 'secret_field.dart';
import 'synthetic.dart';
import 'theme.dart';

/// iOS 用可左滑返回的 Cupertino 转场，其余用 Material 转场和系统返回键。
PageRoute<void> adaptiveRoute(Widget page) => defaultTargetPlatform == TargetPlatform.iOS
    ? CupertinoPageRoute<void>(builder: (_) => page)
    : MaterialPageRoute<void>(builder: (_) => page);

const _actions = ['编辑', '复制为新条目', '查看历史', '移到回收站'];

/// 移动体验基线要求 iOS 用操作表、Android 用 Material 底部面板。forui 两端长一样，所以这里按平台分开写。
Future<void> showEntryActions(BuildContext context) {
  if (defaultTargetPlatform == TargetPlatform.iOS) {
    return showCupertinoModalPopup<void>(
      context: context,
      builder: (context) => CupertinoActionSheet(
        actions: [
          for (final label in _actions)
            CupertinoActionSheetAction(onPressed: () => Navigator.pop(context), child: Text(label)),
        ],
        cancelButton: CupertinoActionSheetAction(
          isDefaultAction: true,
          onPressed: () => Navigator.pop(context),
          child: const Text('取消'),
        ),
      ),
    );
  }
  return showModalBottomSheet<void>(
    context: context,
    showDragHandle: true,
    builder: (context) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final label in _actions) ListTile(title: Text(label), onTap: () => Navigator.pop(context)),
        ],
      ),
    ),
  );
}

class DetailPage extends StatelessWidget {
  const DetailPage({super.key, required this.entry});

  final SyntheticEntry entry;

  @override
  Widget build(BuildContext context) {
    const gap = SizedBox(height: 16);
    return FScaffold(
      // forui 的页头标题写死单行，这里显式放宽到两行；完整标题在下面的“标题”框里。
      header: FHeader.nested(
        title: Text(entry.title, maxLines: 2, softWrap: true, overflow: TextOverflow.ellipsis),
        prefixes: [backAction(context)],
        suffixes: [
          FHeaderAction(
            style: keexHeaderActionStyle,
            icon: const Icon(FLucideIcons.ellipsis),
            semanticsLabel: '更多操作',
            onPress: () => showEntryActions(context),
          ),
        ],
      ),
      child: ListView(
        children: [
          FTextField(
            label: const Text('标题'),
            control: FTextFieldControl.managed(initial: TextEditingValue(text: entry.title)),
          ),
          gap,
          FTextField(
            label: const Text('账号'),
            keyboardType: TextInputType.emailAddress,
            control: FTextFieldControl.managed(initial: TextEditingValue(text: entry.account)),
          ),
          gap,
          KeexSecretField(label: '密码', initial: entry.hiddenValue),
          gap,
          FTextField(label: const Text('备注'), hint: '可以写中文', maxLines: 4),
          gap,
          const KeexDateField(label: '到期日'),
          gap,
          OtpPreview(code: entry.otp),
          gap,
          // forui 默认的 md 按钮在 Android 上只有 44dp 高，换成 lg 才到 48dp。
          FButton(
            size: .lg,
            prefix: const Icon(FLucideIcons.copy),
            onPress: () => showFToast(context: context, title: const Text('演示页面，没有真的复制')),
            child: const Text('复制密码'),
          ),
          gap,
        ],
      ),
    );
  }
}

Widget backAction(BuildContext context) => FHeaderAction.back(
  style: keexHeaderActionStyle,
  semanticsLabel: '返回',
  onPress: () => Navigator.of(context).maybePop(),
);

/// 对照组：forui 自带的密码框，测试比对它默认发给系统的输入法和自动填充配置。
/// 单独一页，免得它的 40×40 显示按钮混进对 keex 自己组件的无障碍检查。
class BuiltinPasswordPage extends StatelessWidget {
  const BuiltinPasswordPage({super.key});

  @override
  Widget build(BuildContext context) => FScaffold(
    header: FHeader.nested(title: const Text('对照：forui 自带密码框'), prefixes: [backAction(context)]),
    child: ListView(
      children: [
        FTextField.password(
          label: const Text('forui 自带密码框'),
          control: FTextFieldControl.managed(initial: TextEditingValue(text: const SyntheticEntry(0).hiddenValue)),
        ),
      ],
    ),
  );
}
