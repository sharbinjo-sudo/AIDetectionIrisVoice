import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/core/theme/app_theme.dart';
import 'package:frontend/core/widgets/mobile_navigation_drawer.dart';
import 'package:frontend/features/test_mode/presentation/widgets/test_mode_selector.dart';

void main() {
  testWidgets('test mode selector renders stacked mobile actions', (
    tester,
  ) async {
    TestPanelType? selected;

    await tester.pumpWidget(
      _TestApp(
        child: Scaffold(
          body: TestModeSelector(
            selected: TestPanelType.iris,
            stacked: true,
            onSelected: (value) => selected = value,
          ),
        ),
      ),
    );

    expect(find.text('Test Iris Camera'), findsOneWidget);
    expect(find.text('Test Voice Recognition'), findsOneWidget);

    await tester.tap(find.text('Test Voice Recognition'));
    await tester.pump();

    expect(selected, TestPanelType.voice);
  });

  testWidgets('test mode selector renders segmented desktop control', (
    tester,
  ) async {
    await tester.pumpWidget(
      _TestApp(
        child: Scaffold(
          body: TestModeSelector(
            selected: TestPanelType.voice,
            stacked: false,
            onSelected: (_) {},
          ),
        ),
      ),
    );

    expect(find.byType(SegmentedButton<TestPanelType>), findsOneWidget);
    expect(find.text('Test Iris Camera'), findsOneWidget);
    expect(find.text('Test Voice Recognition'), findsOneWidget);
  });

  testWidgets('mobile navigation drawer shows primary routes', (tester) async {
    await tester.pumpWidget(
      const _TestApp(
        child: Scaffold(
          drawer: MobileNavigationDrawer(currentLocation: '/test'),
        ),
      ),
    );

    final scaffoldState = tester.state<ScaffoldState>(find.byType(Scaffold));
    scaffoldState.openDrawer();
    await tester.pumpAndSettle();

    expect(find.text('BioFusion AI'), findsOneWidget);
    expect(find.text('Home'), findsOneWidget);
    expect(find.text('Test'), findsOneWidget);
    expect(find.text('IRL'), findsOneWidget);
  });
}

class _TestApp extends StatelessWidget {
  const _TestApp({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(theme: AppTheme.light(), home: child);
  }
}
