import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../../../core/config/api_endpoints.dart';
import '../models/iris_tracking_result.dart';

class IrisTrackingRepository {
  const IrisTrackingRepository(this._dio);

  final Dio _dio;

  Future<IrisTrackingFrame> track(Uint8List jpegBytes) async {
    final response = await _dio.post<dynamic>(
      ApiEndpoints.irisTracking,
      data: FormData.fromMap({
        'frame': MultipartFile.fromBytes(
          jpegBytes,
          filename: 'tracking_frame.jpg',
        ),
      }),
    );
    final envelope = response.data is Map<String, dynamic>
        ? response.data as Map<String, dynamic>
        : const <String, dynamic>{};
    final data =
        (envelope['data'] as Map?)?.cast<String, dynamic>() ?? envelope;
    return IrisTrackingFrame.fromJson(data);
  }
}
