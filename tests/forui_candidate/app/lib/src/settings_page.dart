import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

import 'detail_page.dart';

/// 设置页只演示分组列表的样子；状态文字照 CAPABILITIES 的规则写“未配置”“未启用”，不放假开关。
class SettingsPage extends StatelessWidget {
  const SettingsPage({super.key});

  @override
  Widget build(BuildContext context) {
    FTile row(IconData icon, String title, String detail) => FTile(
      prefix: Icon(icon),
      title: Text(title),
      details: Text(detail),
      suffix: const Icon(FLucideIcons.chevronRight),
      onPress: () {},
    );
    return ListView(
      children: [
        FTileGroup(
          label: const Text('密码库'),
          children: [
            row(FLucideIcons.database, '当前密码库', '合成样本.kdbx'),
            row(FLucideIcons.copy, '同步与备份', '未配置同步'),
          ],
        ),
        const SizedBox(height: 16),
        FTileGroup(
          label: const Text('安全'),
          children: [
            row(FLucideIcons.keyRound, '自动填充', '未启用'),
            row(FLucideIcons.shieldCheck, '生物识别解锁', '未开通'),
          ],
        ),
        const SizedBox(height: 16),
        FTileGroup(
          label: const Text('外观与语言'),
          children: [
            row(FLucideIcons.eye, '深浅色', '跟随系统'),
            row(FLucideIcons.settings, '语言', '简体中文'),
          ],
        ),
        const SizedBox(height: 16),
        FTileGroup(
          label: const Text('实验对照'),
          children: [
            FTile(
              prefix: const Icon(FLucideIcons.keyRound),
              title: const Text('forui 自带密码框'),
              suffix: const Icon(FLucideIcons.chevronRight),
              onPress: () => Navigator.of(context).push(adaptiveRoute(const BuiltinPasswordPage())),
            ),
          ],
        ),
      ],
    );
  }
}
