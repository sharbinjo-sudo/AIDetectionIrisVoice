import 'dart:ui';

class IrisTrackingResult {
  const IrisTrackingResult({
    required this.eyeSide,
    required this.detected,
    required this.confidence,
    required this.stable,
    required this.sourceSize,
    required this.center,
    required this.irisWidth,
    required this.irisHeight,
    required this.radius,
    required this.angleDegrees,
    required this.circularity,
    required this.contour,
    required this.eyeRoi,
  });

  final String eyeSide;
  final bool detected;
  final double confidence;
  final bool stable;
  final Size sourceSize;
  final Offset center;
  final double irisWidth;
  final double irisHeight;
  final double radius;
  final double angleDegrees;
  final double circularity;
  final List<Offset> contour;
  final Rect? eyeRoi;

  factory IrisTrackingResult.fromJson(Map<String, dynamic> json) {
    final detected = json['detected'] == true;
    final rawContour = json['contour'] as List? ?? const [];
    return IrisTrackingResult(
      eyeSide: json['eye_side'] as String? ?? 'UNKNOWN',
      detected: detected,
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
      stable: json['stable'] == true,
      sourceSize: Size(
        (json['frame_width'] as num?)?.toDouble() ?? 0,
        (json['frame_height'] as num?)?.toDouble() ?? 0,
      ),
      center: Offset(
        (json['center_x'] as num?)?.toDouble() ?? 0,
        (json['center_y'] as num?)?.toDouble() ?? 0,
      ),
      irisWidth: (json['iris_width'] as num?)?.toDouble() ?? 0,
      irisHeight: (json['iris_height'] as num?)?.toDouble() ?? 0,
      radius: (json['radius'] as num?)?.toDouble() ?? 0,
      angleDegrees: (json['angle_degrees'] as num?)?.toDouble() ?? 0,
      circularity: (json['circularity'] as num?)?.toDouble() ?? 0,
      contour: rawContour
          .whereType<List>()
          .where((point) => point.length >= 2)
          .map(
            (point) => Offset(
              (point[0] as num).toDouble(),
              (point[1] as num).toDouble(),
            ),
          )
          .toList(growable: false),
      eyeRoi: _rectFromJson(json['eye_roi']),
    );
  }

  static Rect? _rectFromJson(dynamic value) {
    if (value is! Map) {
      return null;
    }
    final map = value.cast<Object?, Object?>();
    final x = (map['x'] as num?)?.toDouble();
    final y = (map['y'] as num?)?.toDouble();
    final width = (map['width'] as num?)?.toDouble();
    final height = (map['height'] as num?)?.toDouble();
    if (x == null || y == null || width == null || height == null) {
      return null;
    }
    return Rect.fromLTWH(x, y, width, height);
  }

  bool get hasValidGeometry {
    return detected &&
        sourceSize.width > 0 &&
        sourceSize.height > 0 &&
        center.dx.isFinite &&
        center.dy.isFinite &&
        irisWidth >= 4 &&
        irisHeight >= 4;
  }

  IrisTrackingResult copyWithGeometry({
    required Offset center,
    required double irisWidth,
    required double irisHeight,
    required double radius,
    required double angleDegrees,
  }) {
    return IrisTrackingResult(
      eyeSide: eyeSide,
      detected: detected,
      confidence: confidence,
      stable: stable,
      sourceSize: sourceSize,
      center: center,
      irisWidth: irisWidth,
      irisHeight: irisHeight,
      radius: radius,
      angleDegrees: angleDegrees,
      circularity: circularity,
      contour: contour,
      eyeRoi: eyeRoi,
    );
  }
}

class IrisTrackingFrame {
  const IrisTrackingFrame({
    required this.sourceSize,
    required this.eyes,
    required this.eyeRois,
  });

  final Size sourceSize;
  final List<IrisTrackingResult> eyes;
  final List<Rect> eyeRois;

  bool get detected => eyes.any((eye) => eye.hasValidGeometry);

  factory IrisTrackingFrame.fromJson(Map<String, dynamic> json) {
    final sourceSize = Size(
      (json['frame_width'] as num?)?.toDouble() ?? 0,
      (json['frame_height'] as num?)?.toDouble() ?? 0,
    );
    final rawEyes = json['eyes'] as List? ?? const [];
    final eyes = rawEyes
        .whereType<Map>()
        .map(
          (eye) => IrisTrackingResult.fromJson({
            ...json,
            ...eye.cast<String, dynamic>(),
          }),
        )
        .where((eye) => eye.hasValidGeometry)
        .toList(growable: false);
    final rawRois = json['eye_rois'] as List? ?? const [];
    final eyeRois = rawRois
        .map(IrisTrackingResult._rectFromJson)
        .whereType<Rect>()
        .toList(growable: false);

    // Keep compatibility with a backend returning the original single-eye
    // payload while deployments are restarted independently.
    final compatibleEyes = eyes.isEmpty && json['detected'] == true
        ? [IrisTrackingResult.fromJson(json)]
        : eyes;
    return IrisTrackingFrame(
      sourceSize: sourceSize,
      eyes: compatibleEyes,
      eyeRois: eyeRois,
    );
  }
}
