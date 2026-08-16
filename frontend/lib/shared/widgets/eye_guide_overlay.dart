import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../core/theme/app_colours.dart';

class EyeGuideOverlay extends StatefulWidget {
  const EyeGuideOverlay({super.key});

  @override
  State<EyeGuideOverlay> createState() => _EyeGuideOverlayState();
}

class _EyeGuideOverlayState extends State<EyeGuideOverlay>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1800),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) {
          return CustomPaint(
            painter: _BiometricFaceGuidePainter(
              progress: _controller.value,
              textDirection: Directionality.of(context),
            ),
          );
        },
      ),
    );
  }
}

class _BiometricFaceGuidePainter extends CustomPainter {
  const _BiometricFaceGuidePainter({
    required this.progress,
    required this.textDirection,
  });

  final double progress;
  final TextDirection textDirection;

  @override
  void paint(Canvas canvas, Size size) {
    final shortest = math.min(size.width, size.height);
    final center = Offset(size.width / 2, size.height / 2);
    final faceRect = Rect.fromCenter(
      center: center.translate(0, shortest * 0.02),
      width: shortest * 0.64,
      height: shortest * 0.82,
    );
    final eyeCenter = center.translate(0, -shortest * 0.08);
    final irisRadius = shortest * 0.115;

    final scrimPaint = Paint()..color = Colors.black.withValues(alpha: 0.22);
    final clearPath = Path()
      ..addOval(faceRect)
      ..addOval(Rect.fromCircle(center: eyeCenter, radius: irisRadius * 1.25));
    canvas.saveLayer(Offset.zero & size, Paint());
    canvas.drawRect(Offset.zero & size, scrimPaint);
    canvas.drawPath(clearPath, Paint()..blendMode = BlendMode.clear);
    canvas.restore();

    _drawFaceFrame(canvas, faceRect);
    _drawIrisTarget(canvas, eyeCenter, irisRadius);
    _drawTrackingDots(canvas, faceRect, shortest);
    _drawScanLine(canvas, faceRect);
    _drawLabel(canvas, size, eyeCenter, irisRadius);
  }

  void _drawFaceFrame(Canvas canvas, Rect faceRect) {
    final facePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.4
      ..color = Colors.white.withValues(alpha: 0.92);
    final glowPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 7
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 7)
      ..color = AppColours.cyan.withValues(alpha: 0.35);

    canvas.drawOval(faceRect, glowPaint);
    canvas.drawOval(faceRect, facePaint);

    final bracketPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round
      ..color = AppColours.cyan;
    final corner = math.min(faceRect.width, faceRect.height) * 0.12;
    final corners = [
      faceRect.topLeft,
      faceRect.topRight,
      faceRect.bottomLeft,
      faceRect.bottomRight,
    ];

    for (final point in corners) {
      final left = point.dx == faceRect.left;
      final top = point.dy == faceRect.top;
      final horizontalEnd = Offset(
        point.dx + (left ? corner : -corner),
        point.dy,
      );
      final verticalEnd = Offset(point.dx, point.dy + (top ? corner : -corner));
      canvas.drawLine(point, horizontalEnd, bracketPaint);
      canvas.drawLine(point, verticalEnd, bracketPaint);
    }
  }

  void _drawIrisTarget(Canvas canvas, Offset eyeCenter, double radius) {
    final pulse = 0.82 + (progress * 0.18);
    final irisPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3
      ..color = AppColours.success;
    final pulsePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2
      ..color = AppColours.success.withValues(alpha: 0.42);
    final crosshairPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5
      ..strokeCap = StrokeCap.round
      ..color = Colors.white.withValues(alpha: 0.9);

    canvas.drawCircle(eyeCenter, radius * 1.45 * pulse, pulsePaint);
    canvas.drawCircle(eyeCenter, radius, irisPaint);
    canvas.drawCircle(eyeCenter, radius * 0.42, irisPaint..strokeWidth = 2);
    canvas.drawLine(
      eyeCenter.translate(-radius * 1.55, 0),
      eyeCenter.translate(-radius * 0.72, 0),
      crosshairPaint,
    );
    canvas.drawLine(
      eyeCenter.translate(radius * 0.72, 0),
      eyeCenter.translate(radius * 1.55, 0),
      crosshairPaint,
    );
    canvas.drawLine(
      eyeCenter.translate(0, -radius * 1.55),
      eyeCenter.translate(0, -radius * 0.72),
      crosshairPaint,
    );
    canvas.drawLine(
      eyeCenter.translate(0, radius * 0.72),
      eyeCenter.translate(0, radius * 1.55),
      crosshairPaint,
    );
  }

  void _drawTrackingDots(Canvas canvas, Rect faceRect, double shortest) {
    final dotPaint = Paint()..color = Colors.white.withValues(alpha: 0.92);
    final activePaint = Paint()..color = AppColours.cyan;
    final radius = shortest * 0.011;
    final points = [
      Offset(faceRect.center.dx, faceRect.top + faceRect.height * 0.20),
      Offset(
        faceRect.left + faceRect.width * 0.30,
        faceRect.top + faceRect.height * 0.35,
      ),
      Offset(
        faceRect.right - faceRect.width * 0.30,
        faceRect.top + faceRect.height * 0.35,
      ),
      Offset(
        faceRect.left + faceRect.width * 0.36,
        faceRect.top + faceRect.height * 0.55,
      ),
      Offset(
        faceRect.right - faceRect.width * 0.36,
        faceRect.top + faceRect.height * 0.55,
      ),
      Offset(faceRect.center.dx, faceRect.top + faceRect.height * 0.72),
    ];

    for (var i = 0; i < points.length; i += 1) {
      final paint =
          i == (progress * points.length).floor().clamp(0, points.length - 1)
          ? activePaint
          : dotPaint;
      canvas.drawCircle(points[i], radius, paint);
    }
  }

  void _drawScanLine(Canvas canvas, Rect faceRect) {
    final y = faceRect.top + (faceRect.height * (0.18 + progress * 0.64));
    final scanPaint = Paint()
      ..shader = LinearGradient(
        colors: [
          AppColours.cyan.withValues(alpha: 0.0),
          AppColours.cyan.withValues(alpha: 0.85),
          AppColours.cyan.withValues(alpha: 0.0),
        ],
      ).createShader(Rect.fromLTWH(faceRect.left, y - 2, faceRect.width, 4))
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round;

    canvas.drawLine(
      Offset(faceRect.left + faceRect.width * 0.18, y),
      Offset(faceRect.right - faceRect.width * 0.18, y),
      scanPaint,
    );
  }

  void _drawLabel(
    Canvas canvas,
    Size size,
    Offset eyeCenter,
    double irisRadius,
  ) {
    final label = 'Center one eye in the green iris ring';
    final painter = TextPainter(
      text: TextSpan(
        text: label,
        style: const TextStyle(
          color: Colors.white,
          fontSize: 13,
          fontWeight: FontWeight.w700,
        ),
      ),
      textAlign: TextAlign.center,
      textDirection: textDirection,
    )..layout(maxWidth: size.width * 0.78);

    final padding = const EdgeInsets.symmetric(horizontal: 12, vertical: 7);
    final labelSize = Size(
      painter.width + padding.horizontal,
      painter.height + padding.vertical,
    );
    final labelRect = RRect.fromRectAndRadius(
      Rect.fromCenter(
        center: Offset(
          size.width / 2,
          math.min(
            size.height - labelSize.height,
            eyeCenter.dy + irisRadius * 2.3,
          ),
        ),
        width: labelSize.width,
        height: labelSize.height,
      ),
      const Radius.circular(999),
    );

    canvas.drawRRect(
      labelRect,
      Paint()..color = AppColours.deepNavy.withValues(alpha: 0.76),
    );
    painter.paint(
      canvas,
      Offset(
        labelRect.outerRect.left + padding.left,
        labelRect.outerRect.top + padding.top,
      ),
    );
  }

  @override
  bool shouldRepaint(covariant _BiometricFaceGuidePainter oldDelegate) {
    return oldDelegate.progress != progress ||
        oldDelegate.textDirection != textDirection;
  }
}
