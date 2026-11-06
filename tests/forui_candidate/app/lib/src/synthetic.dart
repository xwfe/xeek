/// 1 万条公开合成条目。名字、账号、密码都是编的，不含任何真实资料。
library;

enum EntryKind {
  login('登录'),
  api('API 凭据'),
  note('安全备注');

  const EntryKind(this.label);

  final String label;
}

final class SyntheticEntry {
  const SyntheticEntry(this.index);

  final int index;

  static const _sites = ['示例银行', '演示邮箱', '测试云盘', '样例社交', '虚构商城', '合成论坛', '模拟视频', 'Example Git', '假想地图', '练习笔记'];

  String get number => index.toString().padLeft(5, '0');

  String get title => '${_sites[index % _sites.length]} $number';

  String get account => 'user$number@example.com';

  EntryKind get kind => EntryKind.values[index % EntryKind.values.length];

  bool get favorite => index % 17 == 0;

  /// 只在详情页的秘密输入框里出现；测试核对它不会进读屏树和网页 DOM。
  String get hiddenValue => 'Kx-synth-$number!';

  /// 动态口令示意值，同样不该被读屏自动念出。
  String get otp => (100000 + index * 7919 % 900000).toString();

  bool matches(String query) {
    final q = query.toLowerCase();
    return title.toLowerCase().contains(q) || account.contains(q);
  }
}

final List<SyntheticEntry> syntheticEntries = List.generate(10000, SyntheticEntry.new, growable: false);
