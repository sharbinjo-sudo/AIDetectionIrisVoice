import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/core/config/app_config.dart';
import 'package:frontend/core/theme/app_theme.dart';
import 'package:frontend/core/widgets/mobile_navigation_drawer.dart';
import 'package:frontend/features/home/presentation/banking_auth_page.dart';
import 'package:frontend/features/home/data/banking_auth_repository.dart';
import 'package:frontend/features/test_mode/presentation/widgets/test_mode_selector.dart';
import 'package:frontend/features/test_mode/presentation/test_page.dart';

void main() {
  testWidgets('iris analysis waits for a captured sample', (tester) async {
    const permissions = MethodChannel(
      'flutter.baseflow.com/permissions/methods',
    );
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      permissions,
      (call) async => <int, int>{1: 0},
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        permissions,
        null,
      ),
    );
    await tester.pumpWidget(
      const ProviderScope(
        child: _TestApp(child: Scaffold(body: TestPage())),
      ),
    );
    await tester.pumpAndSettle();
    final button = find.widgetWithText(FilledButton, 'Analyse Iris Quality');
    await tester.scrollUntilVisible(button, 300);
    expect(tester.widget<FilledButton>(button).onPressed, isNull);
    expect(find.text('Capture a sample to enable analysis.'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  test('backend URL normalization adds the API root and removes slashes', () {
    expect(
      AppConfig.normalizeBaseUrl('http://127.0.0.1:8000/'),
      'http://127.0.0.1:8000/api/v1',
    );
    expect(
      AppConfig.normalizeBaseUrl('http://localhost:8000/api/v1///'),
      'http://localhost:8000/api/v1',
    );
  });

  test('backend URL validation rejects incomplete and ambiguous addresses', () {
    expect(AppConfig.validateBaseUrl('localhost:8000'), isNotNull);
    expect(
      AppConfig.validateBaseUrl('http://localhost:8000/api/v1?debug=true'),
      isNotNull,
    );
    expect(AppConfig.validateBaseUrl('http://localhost:8000/api/v1'), isNull);
  });

  test('banking session preserves the enrolled eye for verification', () {
    final session = BankingAuthSession.fromEnvelope({
      'data': {
        'token': 'signed-token',
        'next_step': 'BIOMETRIC_VERIFICATION',
        'customer': {
          'customer_id': '123456',
          'biometric_user_id': 'user-id',
          'enrollment_status': 'COMPLETE',
          'enrolled_eye_side': 'RIGHT',
        },
      },
    });

    expect(session.enrolledEyeSide, 'RIGHT');
  });

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

    expect(find.text('Test Iris Quality'), findsOneWidget);
    expect(find.text('Test Voice Quality'), findsOneWidget);

    await tester.tap(find.text('Test Voice Quality'));
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
    expect(find.text('Test Iris Quality'), findsOneWidget);
    expect(find.text('Test Voice Quality'), findsOneWidget);
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

    expect(find.text('Advanced Human Recognition'), findsOneWidget);
    expect(find.text('Home'), findsOneWidget);
    expect(find.text('Test'), findsOneWidget);
    expect(find.text('Login'), findsNothing);
    expect(find.text('Register'), findsNothing);
    expect(find.text('Settings'), findsOneWidget);
    expect(find.text('IRL'), findsNothing);
  });

  testWidgets('registration does not request generated banking identifiers', (
    tester,
  ) async {
    await tester.pumpWidget(
      const ProviderScope(child: _TestApp(child: BankingAuthPage.register())),
    );

    expect(find.text('Full name'), findsOneWidget);
    expect(find.text('Mobile number'), findsOneWidget);
    expect(find.text('Password'), findsNothing);
    expect(find.text('4-digit PIN'), findsOneWidget);
    expect(find.text('Bank account number'), findsNothing);
    expect(find.text('Customer ID'), findsNothing);
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
