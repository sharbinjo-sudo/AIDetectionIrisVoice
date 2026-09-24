import 'dart:math' as math;
import 'dart:ui';

import '../../../core/tracking/one_euro_filter.dart';
import 'iris_tracking_result.dart';

class IrisTrackingFilter {
  // Results arrive a few times per second rather than at display refresh
  // rate. These cutoffs retain One Euro's jitter suppression when still, but
  // let the tracker converge promptly after a real eye/head movement.
  final _centerX = OneEuroFilter(minCutoff: 2.2, beta: 0.12);
  final _centerY = OneEuroFilter(minCutoff: 2.2, beta: 0.12);
  final _width = OneEuroFilter(minCutoff: 1.7, beta: 0.07);
  final _height = OneEuroFilter(minCutoff: 1.7, beta: 0.07);
  final _radius = OneEuroFilter(minCutoff: 1.7, beta: 0.07);
  final _angleCos = OneEuroFilter(minCutoff: 1.8, beta: 0.08);
  final _angleSin = OneEuroFilter(minCutoff: 1.8, beta: 0.08);

  IrisTrackingResult? _lastAccepted;
  double? _lastDetectionTimestamp;

  IrisTrackingResult? filter(
    IrisTrackingResult detection,
    double timestampSeconds,
  ) {
    if (!detection.hasValidGeometry) {
      markLost(timestampSeconds);
      return null;
    }

    final last = _lastAccepted;
    final lastTimestamp = _lastDetectionTimestamp;
    if (last != null && lastTimestamp != null) {
      final gap = timestampSeconds - lastTimestamp;
      if (gap > 0.65 || last.sourceSize != detection.sourceSize) {
        reset();
      } else {
        final displacement = (detection.center - last.center).distance;
        final allowedJump = math.max(
          detection.radius * 6,
          detection.sourceSize.shortestSide * 0.18,
        );
        if (displacement > allowedJump) {
          markLost(timestampSeconds);
          return null;
        }
      }
    }

    final radians = detection.angleDegrees * math.pi / 180;
    final doubledCosine = math.cos(radians * 2);
    final doubledSine = math.sin(radians * 2);
    final filteredCosine = _angleCos.filter(doubledCosine, timestampSeconds);
    final filteredSine = _angleSin.filter(doubledSine, timestampSeconds);
    var filteredAngle = math.atan2(filteredSine, filteredCosine) * 90 / math.pi;
    if (filteredAngle < 0) {
      filteredAngle += 180;
    }

    final filtered = detection.copyWithGeometry(
      center: Offset(
        _centerX.filter(detection.center.dx, timestampSeconds),
        _centerY.filter(detection.center.dy, timestampSeconds),
      ),
      irisWidth: _width.filter(detection.irisWidth, timestampSeconds),
      irisHeight: _height.filter(detection.irisHeight, timestampSeconds),
      radius: _radius.filter(detection.radius, timestampSeconds),
      angleDegrees: filteredAngle,
    );
    _lastAccepted = filtered;
    _lastDetectionTimestamp = timestampSeconds;
    return filtered;
  }

  void markLost(double timestampSeconds) {
    final lastTimestamp = _lastDetectionTimestamp;
    if (lastTimestamp != null && timestampSeconds - lastTimestamp > 0.65) {
      reset();
    }
  }

  void reset() {
    _centerX.reset();
    _centerY.reset();
    _width.reset();
    _height.reset();
    _radius.reset();
    _angleCos.reset();
    _angleSin.reset();
    _lastAccepted = null;
    _lastDetectionTimestamp = null;
  }
}
