import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../../core/theme/app_colours.dart';
import '../../features/test_mode/models/iris_tracking_result.dart';

class CameraPreviewTransform {
  const CameraPreviewTransform({
    required this.sourceSize,
    required this.viewportSize,
    required this.fit,
    required this.mirrorHorizontally,
  });

  final Size sourceSize;
  final Size viewportSize;
  final BoxFit fit;
  final bool mirrorHorizontally;

  double get scale {
    final scaleX = viewportSize.width / sourceSize.width;
    final scaleY = viewportSize.height / sourceSize.height;
    return fit == BoxFit.contain
        ? math.min(scaleX, scaleY)
        : math.max(scaleX, scaleY);
  }

  Offset get offset {
    final rendered = Size(sourceSize.width * scale, sourceSize.height * scale);
    return Offset(
      (viewportSize.width - rendered.width) / 2,
      (viewportSize.height - rendered.height) / 2,
    );
  }

  Offset transformPoint(Offset sourcePoint) {
    final x = mirrorHorizontally
        ? sourceSize.width - sourcePoint.dx
        : sourcePoint.dx;
    return offset + Offset(x * scale, sourcePoint.dy * scale);
  }

  void applyToCanvas(Canvas canvas) {
    canvas.translate(offset.dx, offset.dy);
    canvas.scale(scale);
    if (mirrorHorizontally) {
      canvas.translate(sourceSize.width, 0);
      canvas.scale(-1, 1);
    }
  }
}

class IrisTrackingOverlay extends StatefulWidget {
  const IrisTrackingOverlay({
    super.key,
    required this.tracking,
    this.eyeRois = const [],
    required this.sourceSize,
    required this.fit,
    required this.mirrorHorizontally,
    this.showTracker = true,
    this.debugMode = false,
  });

  final List<IrisTrackingResult> tracking;
  final List<Rect> eyeRois;
  final Size sourceSize;
  final BoxFit fit;
  final bool mirrorHorizontally;
  final bool showTracker;
  final bool debugMode;

  @override
  State<IrisTrackingOverlay> createState() => _IrisTrackingOverlayState();
}

class _IrisTrackingOverlayState extends State<IrisTrackingOverlay>
    with SingleTickerProviderStateMixin {
  static const _transitionDuration = Duration(milliseconds: 90);

  late final AnimationController _controller;
  List<IrisTrackingResult> _from = const [];
  List<IrisTrackingResult> _to = const [];

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: _transitionDuration,
      value: 1,
    );
    _to = widget.tracking;
  }

  @override
  void didUpdateWidget(covariant IrisTrackingOverlay oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (identical(oldWidget.tracking, widget.tracking)) {
      return;
    }

    if (widget.tracking.isEmpty) {
      // A lost detection must remove the production tracker immediately.
      _controller.stop();
      _from = const [];
      _to = const [];
      _controller.value = 1;
      return;
    }

    _from = _interpolatedTracking(_easedProgress);
    _to = widget.tracking;
    _controller.forward(from: 0);
  }

  double get _easedProgress =>
      Curves.easeOutCubic.transform(_controller.value.clamp(0.0, 1.0));

  List<IrisTrackingResult> _interpolatedTracking(double progress) {
    if (_to.isEmpty || progress >= 1) {
      return _to;
    }
    return _to
        .map((target) {
          IrisTrackingResult? start;
          for (final candidate in _from) {
            if (candidate.eyeSide == target.eyeSide) {
              start = candidate;
              break;
            }
          }
          if (start == null || start.sourceSize != target.sourceSize) {
            return target;
          }
          return target.copyWithGeometry(
            center: Offset.lerp(start.center, target.center, progress)!,
            irisWidth: ui.lerpDouble(
              start.irisWidth,
              target.irisWidth,
              progress,
            )!,
            irisHeight: ui.lerpDouble(
              start.irisHeight,
              target.irisHeight,
              progress,
            )!,
            radius: ui.lerpDouble(start.radius, target.radius, progress)!,
            angleDegrees: _lerpEllipseAngle(
              start.angleDegrees,
              target.angleDegrees,
              progress,
            ),
          );
        })
        .toList(growable: false);
  }

  double _lerpEllipseAngle(double start, double end, double progress) {
    var difference = (end - start) % 180;
    if (difference > 90) difference -= 180;
    if (difference < -90) difference += 180;
    final angle = (start + difference * progress) % 180;
    return angle < 0 ? angle + 180 : angle;
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final trackerVisible = widget.showTracker && widget.tracking.isNotEmpty;
    final debugVisible = widget.debugMode && widget.eyeRois.isNotEmpty;
    if (!trackerVisible && !debugVisible) {
      return const SizedBox.shrink();
    }
    return IgnorePointer(
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) => CustomPaint(
          painter: IrisTrackingPainter(
            tracking: widget.showTracker
                ? _interpolatedTracking(_easedProgress)
                : const [],
            eyeRois: widget.eyeRois,
            sourceSize: widget.sourceSize,
            fit: widget.fit,
            mirrorHorizontally: widget.mirrorHorizontally,
            debugMode: widget.debugMode,
          ),
        ),
      ),
    );
  }
}

class IrisTrackingPainter extends CustomPainter {
  const IrisTrackingPainter({
    required this.tracking,
    required this.eyeRois,
    required this.sourceSize,
    required this.fit,
    required this.mirrorHorizontally,
    required this.debugMode,
  });

  final List<IrisTrackingResult> tracking;
  final List<Rect> eyeRois;
  final Size sourceSize;
  final BoxFit fit;
  final bool mirrorHorizontally;
  final bool debugMode;

  @override
  void paint(Canvas canvas, Size size) {
    if (sourceSize.isEmpty || size.isEmpty) {
      return;
    }
    final transform = CameraPreviewTransform(
      sourceSize: sourceSize,
      viewportSize: size,
      fit: fit,
      mirrorHorizontally: mirrorHorizontally,
    );
    canvas.save();
    canvas.clipRect(Offset.zero & size);
    transform.applyToCanvas(canvas);

    if (debugMode) {
      final roiPaint = Paint()
        ..color = Colors.amber.withValues(alpha: 0.78)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1 / transform.scale
        ..isAntiAlias = true;
      for (final roi in eyeRois) {
        canvas.drawRect(roi, roiPaint);
      }
    }

    for (final eye in tracking.where((eye) => eye.hasValidGeometry)) {
      _drawTracking(canvas, transform.scale, eye);
    }
    canvas.restore();
  }

  void _drawTracking(Canvas canvas, double scale, IrisTrackingResult eye) {
    final uncertain = !eye.stable || eye.confidence < 0.70;
    final axisRatio =
        math.min(eye.irisWidth, eye.irisHeight) /
        math.max(eye.irisWidth, eye.irisHeight);
    final unreliableShape = eye.circularity < 0.55 || axisRatio < 0.55;
    final trackerColor = uncertain ? AppColours.warning : AppColours.success;

    final screenStroke = uncertain ? 1.35 : 1.65;
    final ellipsePaint = Paint()
      ..color = trackerColor.withValues(alpha: uncertain ? 0.82 : 0.96)
      ..style = PaintingStyle.stroke
      ..strokeWidth = screenStroke / scale
      ..isAntiAlias = true;

    canvas.save();
    canvas.translate(eye.center.dx, eye.center.dy);
    canvas.rotate(eye.angleDegrees * math.pi / 180);
    final irisBounds = Rect.fromCenter(
      center: Offset.zero,
      width: eye.irisWidth,
      height: eye.irisHeight,
    );
    canvas.drawOval(irisBounds, ellipsePaint);
    if (unreliableShape) {
      canvas.drawRect(
        irisBounds,
        Paint()
          ..color = AppColours.warning.withValues(alpha: 0.42)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1 / scale
          ..isAntiAlias = true,
      );
    }
    canvas.restore();

    final centerPaint = Paint()
      ..color = trackerColor.withValues(alpha: 0.96)
      ..style = PaintingStyle.fill
      ..isAntiAlias = true;
    canvas.drawCircle(eye.center, 1.75 / scale, centerPaint);

    if (debugMode) {
      _drawDebugGeometry(canvas, scale, eye);
    }
  }

  void _drawDebugGeometry(Canvas canvas, double scale, IrisTrackingResult eye) {
    if (eye.contour.length >= 2) {
      final contourPath = Path()
        ..moveTo(eye.contour.first.dx, eye.contour.first.dy);
      for (final point in eye.contour.skip(1)) {
        contourPath.lineTo(point.dx, point.dy);
      }
      contourPath.close();
      canvas.drawPath(
        contourPath,
        Paint()
          ..color = AppColours.cyan.withValues(alpha: 0.90)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1 / scale
          ..isAntiAlias = true,
      );
    }

    canvas.save();
    canvas.translate(eye.center.dx, eye.center.dy);
    canvas.rotate(eye.angleDegrees * math.pi / 180);
    canvas.drawOval(
      Rect.fromCenter(
        center: Offset.zero,
        width: eye.irisWidth,
        height: eye.irisHeight,
      ),
      Paint()
        ..color = Colors.purpleAccent.withValues(alpha: 0.72)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1 / scale,
    );
    canvas.restore();

    final crosshairRadius = 3.5 / scale;
    final centerPaint = Paint()
      ..color = Colors.redAccent
      ..strokeWidth = 1 / scale
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(
      eye.center.translate(-crosshairRadius, 0),
      eye.center.translate(crosshairRadius, 0),
      centerPaint,
    );
    canvas.drawLine(
      eye.center.translate(0, -crosshairRadius),
      eye.center.translate(0, crosshairRadius),
      centerPaint,
    );
  }

  @override
  bool shouldRepaint(covariant IrisTrackingPainter oldDelegate) {
    return oldDelegate.tracking != tracking ||
        oldDelegate.sourceSize != sourceSize ||
        oldDelegate.eyeRois != eyeRois ||
        oldDelegate.fit != fit ||
        oldDelegate.mirrorHorizontally != mirrorHorizontally ||
        oldDelegate.debugMode != debugMode;
  }
}
