import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/features/test_mode/models/iris_tracking_filter.dart';
import 'package:frontend/features/test_mode/models/iris_tracking_result.dart';
import 'package:frontend/shared/widgets/iris_tracking_overlay.dart';

void main() {
  test('iris tracking result retains source-pixel ellipse and contour', () {
    final result = _detection(center: const Offset(268.8, 177.6));

    expect(result.hasValidGeometry, isTrue);
    expect(result.center, const Offset(268.8, 177.6));
    expect(result.irisWidth, 64);
    expect(result.irisHeight, 58);
    expect(result.contour, hasLength(3));
    expect(result.sourceSize, const Size(640, 480));
  });

  test('tracking frame parses both irises and debug eye ROIs', () {
    final frame = IrisTrackingFrame.fromJson({
      'detected': true,
      'frame_width': 1280,
      'frame_height': 720,
      'eyes': [
        _detectionJson(eyeSide: 'LEFT', center: const Offset(520, 260)),
        _detectionJson(eyeSide: 'RIGHT', center: const Offset(760, 260)),
      ],
      'eye_rois': [
        {'x': 460, 'y': 220, 'width': 120, 'height': 90},
        {'x': 700, 'y': 220, 'width': 120, 'height': 90},
      ],
    });

    expect(frame.detected, isTrue);
    expect(frame.eyes.map((eye) => eye.eyeSide), ['LEFT', 'RIGHT']);
    expect(frame.eyeRois, hasLength(2));
    expect(frame.sourceSize, const Size(1280, 720));
  });

  test('preview transform uses the same centered BoxFit.cover crop', () {
    const transform = CameraPreviewTransform(
      sourceSize: Size(640, 480),
      viewportSize: Size(320, 320),
      fit: BoxFit.cover,
      mirrorHorizontally: false,
    );

    expect(transform.scale, closeTo(2 / 3, 0.0001));
    expect(
      transform.transformPoint(const Offset(320, 240)),
      const Offset(160, 160),
    );
  });

  test('preview transform mirrors in source space before fitting', () {
    const transform = CameraPreviewTransform(
      sourceSize: Size(640, 480),
      viewportSize: Size(320, 320),
      fit: BoxFit.cover,
      mirrorHorizontally: true,
    );

    final mapped = transform.transformPoint(const Offset(160, 240));
    expect(mapped.dx, closeTo(266.6667, 0.001));
    expect(mapped.dy, closeTo(160, 0.001));
  });

  test('One Euro tracker rejects a brief implausible component jump', () {
    final filter = IrisTrackingFilter();
    final first = filter.filter(_detection(center: const Offset(200, 180)), 1);
    final outlier = filter.filter(
      _detection(center: const Offset(600, 450)),
      1.05,
    );

    expect(first, isNotNull);
    expect(outlier, isNull);
  });

  testWidgets('production overlay paints a valid tracker without debug mode', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: SizedBox(
          width: 640,
          height: 480,
          child: IrisTrackingOverlay(
            tracking: [_detection(center: const Offset(320, 240))],
            sourceSize: const Size(640, 480),
            fit: BoxFit.cover,
            mirrorHorizontally: false,
          ),
        ),
      ),
    );

    final overlayPaint = find.descendant(
      of: find.byType(IrisTrackingOverlay),
      matching: find.byType(CustomPaint),
    );
    final paint = tester.widget<CustomPaint>(overlayPaint);
    final painter = paint.painter! as IrisTrackingPainter;
    expect(painter.tracking, hasLength(1));
    expect(painter.debugMode, isFalse);
  });

  testWidgets('production overlay disappears with no valid detection', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: SizedBox(
          width: 640,
          height: 480,
          child: IrisTrackingOverlay(
            tracking: [],
            sourceSize: Size(640, 480),
            fit: BoxFit.cover,
            mirrorHorizontally: false,
          ),
        ),
      ),
    );

    expect(
      find.descendant(
        of: find.byType(IrisTrackingOverlay),
        matching: find.byType(CustomPaint),
      ),
      findsNothing,
    );
  });
}

IrisTrackingResult _detection({required Offset center}) {
  return IrisTrackingResult.fromJson(_detectionJson(center: center));
}

Map<String, dynamic> _detectionJson({
  String eyeSide = 'LEFT',
  required Offset center,
}) {
  return {
    'detected': true,
    'eye_side': eyeSide,
    'confidence': 0.84,
    'stable': true,
    'center_x': center.dx,
    'center_y': center.dy,
    'iris_width': 64.0,
    'iris_height': 58.0,
    'radius': 30.5,
    'angle_degrees': 12.0,
    'circularity': 0.79,
    'contour': [
      [240.0, 177.6],
      [268.8, 150.0],
      [300.0, 177.6],
    ],
    'frame_width': 640,
    'frame_height': 480,
  };
}
