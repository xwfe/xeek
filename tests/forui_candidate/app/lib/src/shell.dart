import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

import 'passwords_page.dart';
import 'settings_page.dart';
import 'theme.dart';

/// 五项一级导航，顺序按 AGENTS.md 固定。窄屏用底栏，720 起用同顺序侧栏（adr/design/README.md §4）。
const tabs = [
  (label: '密码', icon: FLucideIcons.keyRound),
  (label: '验证', icon: FLucideIcons.shieldCheck),
  (label: '证件', icon: FLucideIcons.idCard),
  (label: '银行', icon: FLucideIcons.creditCard),
  (label: '设置', icon: FLucideIcons.settings),
];

class KeexShell extends StatefulWidget {
  const KeexShell({super.key});

  @override
  State<KeexShell> createState() => _KeexShellState();
}

class _KeexShellState extends State<KeexShell> {
  int index = 0;

  @override
  Widget build(BuildContext context) {
    final body = switch (index) {
      0 => const PasswordsPage(),
      4 => const SettingsPage(),
      _ => Center(child: Text('${tabs[index].label}：本实验只做“密码”和“设置”两页')),
    };
    final header = FHeader(title: Text(tabs[index].label));
    if (MediaQuery.sizeOf(context).width >= 720) {
      return FScaffold(
        header: header,
        sidebar: FSidebar(
          children: [
            FSidebarGroup(
              children: [
                for (final (i, tab) in tabs.indexed)
                  FSidebarItem(
                    style: keexSidebarItemStyle,
                    icon: Icon(tab.icon),
                    label: Text(tab.label),
                    selected: i == index,
                    onPress: () => setState(() => index = i),
                  ),
              ],
            ),
          ],
        ),
        child: body,
      );
    }
    return FScaffold(
      header: header,
      footer: FBottomNavigationBar(
        index: index,
        safeAreaBottom: true,
        onChange: (i) => setState(() => index = i),
        children: [for (final tab in tabs) FBottomNavigationBarItem(icon: Icon(tab.icon), label: Text(tab.label))],
      ),
      child: body,
    );
  }
}
