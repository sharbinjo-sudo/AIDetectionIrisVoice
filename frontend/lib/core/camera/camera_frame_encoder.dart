import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:image/image.dart' as image;

const int _maximumTrackingFrameDimension = 960;

Future<Uint8List?> encodeCameraFrame(
  CameraImage frame, {
  required int rotationDegrees,
}) async {
  final payload = <String, Object>{
    'width': frame.width,
    'height': frame.height,
    'format': frame.format.group.name,
    'rotation': rotationDegrees,
    'planes': frame.planes
        .map(
          (plane) => <String, Object>{
            'bytes': Uint8List.fromList(plane.bytes),
            'bytesPerRow': plane.bytesPerRow,
            'bytesPerPixel': plane.bytesPerPixel ?? 1,
          },
        )
        .toList(),
  };
  return compute(_encodeFrame, payload);
}

int cameraFrameRotation(
  CameraDescription camera,
  DeviceOrientation orientation,
) {
  const deviceDegrees = <DeviceOrientation, int>{
    DeviceOrientation.portraitUp: 0,
    DeviceOrientation.landscapeLeft: 90,
    DeviceOrientation.portraitDown: 180,
    DeviceOrientation.landscapeRight: 270,
  };
  final deviceRotation = deviceDegrees[orientation] ?? 0;
  if (camera.lensDirection == CameraLensDirection.front) {
    return (camera.sensorOrientation + deviceRotation) % 360;
  }
  return (camera.sensorOrientation - deviceRotation + 360) % 360;
}

Uint8List? _encodeFrame(Map<String, Object> payload) {
  final width = payload['width']! as int;
  final height = payload['height']! as int;
  final format = payload['format']! as String;
  final rotation = payload['rotation']! as int;
  final planes = (payload['planes']! as List).cast<Map<String, Object>>();

  image.Image? decoded;
  if (format == ImageFormatGroup.bgra8888.name && planes.isNotEmpty) {
    final bytes = planes.first['bytes']! as Uint8List;
    decoded = image.Image.fromBytes(
      width: width,
      height: height,
      bytes: bytes.buffer,
      bytesOffset: bytes.offsetInBytes,
      rowStride: planes.first['bytesPerRow']! as int,
      order: image.ChannelOrder.bgra,
    );
  } else if (format == ImageFormatGroup.yuv420.name && planes.length >= 3) {
    decoded = _decodeYuv420(
      width,
      height,
      planes,
      maximumDimension: _maximumTrackingFrameDimension,
    );
  } else if (format == ImageFormatGroup.jpeg.name && planes.isNotEmpty) {
    decoded = image.decodeJpg(planes.first['bytes']! as Uint8List);
  }

  if (decoded == null) {
    return null;
  }
  if (format != ImageFormatGroup.yuv420.name &&
      (decoded.width > _maximumTrackingFrameDimension ||
          decoded.height > _maximumTrackingFrameDimension)) {
    final scale =
        _maximumTrackingFrameDimension /
        (decoded.width > decoded.height ? decoded.width : decoded.height);
    decoded = image.copyResize(
      decoded,
      width: (decoded.width * scale).round(),
      height: (decoded.height * scale).round(),
      interpolation: image.Interpolation.linear,
    );
  }
  final oriented = rotation == 0
      ? decoded
      : image.copyRotate(decoded, angle: rotation.toDouble());
  return Uint8List.fromList(image.encodeJpg(oriented, quality: 72));
}

image.Image _decodeYuv420(
  int width,
  int height,
  List<Map<String, Object>> planes, {
  required int maximumDimension,
}) {
  final yPlane = planes[0];
  final uPlane = planes[1];
  final vPlane = planes[2];
  final yBytes = yPlane['bytes']! as Uint8List;
  final uBytes = uPlane['bytes']! as Uint8List;
  final vBytes = vPlane['bytes']! as Uint8List;
  final yRowStride = yPlane['bytesPerRow']! as int;
  final uRowStride = uPlane['bytesPerRow']! as int;
  final vRowStride = vPlane['bytesPerRow']! as int;
  final uPixelStride = uPlane['bytesPerPixel']! as int;
  final vPixelStride = vPlane['bytesPerPixel']! as int;
  final sourceMaximum = width > height ? width : height;
  final scale = sourceMaximum > maximumDimension
      ? maximumDimension / sourceMaximum
      : 1.0;
  final outputWidth = (width * scale).round();
  final outputHeight = (height * scale).round();
  final output = image.Image(width: outputWidth, height: outputHeight);

  for (var y = 0; y < outputHeight; y += 1) {
    final sourceY = (y / scale).floor().clamp(0, height - 1);
    final yRow = sourceY * yRowStride;
    final uRow = (sourceY >> 1) * uRowStride;
    final vRow = (sourceY >> 1) * vRowStride;
    for (var x = 0; x < outputWidth; x += 1) {
      final sourceX = (x / scale).floor().clamp(0, width - 1);
      final yIndex = (yRow + sourceX).clamp(0, yBytes.length - 1);
      final uIndex = (uRow + ((sourceX >> 1) * uPixelStride)).clamp(
        0,
        uBytes.length - 1,
      );
      final vIndex = (vRow + ((sourceX >> 1) * vPixelStride)).clamp(
        0,
        vBytes.length - 1,
      );
      final yValue = yBytes[yIndex].toDouble();
      final uValue = uBytes[uIndex].toDouble() - 128.0;
      final vValue = vBytes[vIndex].toDouble() - 128.0;
      final red = (yValue + (1.402 * vValue)).round().clamp(0, 255);
      final green = (yValue - (0.344136 * uValue) - (0.714136 * vValue))
          .round()
          .clamp(0, 255);
      final blue = (yValue + (1.772 * uValue)).round().clamp(0, 255);
      output.setPixelRgb(x, y, red, green, blue);
    }
  }
  return output;
}
