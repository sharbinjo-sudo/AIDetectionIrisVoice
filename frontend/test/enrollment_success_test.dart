import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/features/irl_verification/presentation/widgets/enrollment_success_panel.dart';

void main() {
  for (final width in [320.0, 1280.0]) {
    testWidgets('enrollment success fits $width and offers both actions', (
      tester,
    ) async {
      await tester.binding.setSurfaceSize(Size(width, 640));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      var loginPressed = false;
      var homePressed = false;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: EnrollmentSuccessPanel(
              onLogin: () => loginPressed = true,
              onHome: () => homePressed = true,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Registration complete'), findsOneWidget);
      expect(find.byIcon(Icons.check_rounded), findsOneWidget);
      await tester.ensureVisible(find.text('Go to Login'));
      await tester.tap(find.text('Go to Login'));
      await tester.ensureVisible(find.text('Return Home'));
      await tester.tap(find.text('Return Home'));
      expect(loginPressed, isTrue);
      expect(homePressed, isTrue);
      expect(tester.takeException(), isNull);
    });
  }
}
