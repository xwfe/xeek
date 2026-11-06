// 移动体验基线：iOS 用操作表，Android 用 Material 底部面板。forui 本身两端一样，这一处是我们按平台分开写的。
import 'package:cupertino_ui/cupertino_ui.dart' show CupertinoActionSheet, CupertinoPageRoute;
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';
import 'package:material_ui/material_ui.dart' show BottomSheet, MaterialPageRoute;

import 'helpers.dart';

void main() {
  testWidgets(
    '更多操作和转场按平台分开',
    (tester) async {
      await pumpApp(tester);
      await openFirstEntry(tester);
      final route = ModalRoute.of(tester.element(find.byType(KeyedSubtree).last));
      await tester.tap(find.byIcon(FLucideIcons.ellipsis));
      await tester.pumpAndSettle();
      if (defaultTargetPlatform == TargetPlatform.iOS) {
        expect(find.byType(CupertinoActionSheet), findsOneWidget);
        expect(find.byType(BottomSheet), findsNothing);
        expect(route, isA<CupertinoPageRoute<void>>());
      } else {
        expect(find.byType(BottomSheet), findsOneWidget);
        expect(find.byType(CupertinoActionSheet), findsNothing);
        expect(route, isA<MaterialPageRoute<void>>());
      }
    },
    variant: TargetPlatformVariant(const {TargetPlatform.iOS, TargetPlatform.android}),
  );
}
