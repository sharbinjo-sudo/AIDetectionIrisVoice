import 'dart:developer' as developer;

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import '../../../core/config/api_endpoints.dart';
import '../models/iris_tracking_result.dart';

/// The backend was reached but could not process the tracking frame.
///
/// Deliberately distinct from [IrisTrackingUnavailableException]: an HTTP 422
/// proves the backend is running, so the UI must show the frame/processing
/// reason instead of claiming the backend is unavailable.
class IrisTrackingFailedException implements Exception {
  const IrisTrackingFailedException({required this.message, this.reason});

  /// Human-readable failure description from the backend (``message``).
  final String message;

  /// Optional underlying cause detail (backend ``reason`` field).
  final String? reason;

  @override
  String toString() => reason == null ? message : '$message ($reason)';
}

/// The backend could not be reached at all, or answered with a server error.
class IrisTrackingUnavailableException implements Exception {
  const IrisTrackingUnavailableException(this.message);

  final String message;

  @override
  String toString() => message;
}

class IrisTrackingRepository {
  const IrisTrackingRepository(this._dio);

  final Dio _dio;

  Future<IrisTrackingFrame> track(Uint8List jpegBytes) async {
    final Response<dynamic> response;
    try {
      response = await _dio.post<dynamic>(
        ApiEndpoints.irisTracking,
        data: FormData.fromMap({
          'frame': MultipartFile.fromBytes(
            jpegBytes,
            filename: 'tracking_frame.jpg',
          ),
        }),
      );
    } on DioException catch (error) {
      final statusCode = error.response?.statusCode;
      final data = error.response?.data;
      final payload = data is Map ? data.cast<Object?, Object?>() : null;
      final message =
          payload?['message']?.toString() ??
          payload?['detail']?.toString() ??
          error.message ??
          'The iris tracking request failed.';

      if (statusCode != null && statusCode < 500) {
        // A 4xx means the backend WAS reached: this is a frame/validation or
        // processing failure, never "backend unavailable". Never swallow the
        // backend's reason — surface it to the caller.
        if (kDebugMode) {
          developer.log(
            'iris tracking 4xx: status=$statusCode body=$payload',
            name: 'iris_tracking',
          );
        }
        throw IrisTrackingFailedException(
          message: message,
          reason: payload?['reason']?.toString(),
        );
      }
      // Network failure, connection refused, timeout, or a 5xx: the backend
      // is not usable right now.
      throw IrisTrackingUnavailableException(
        statusCode == null
            ? 'Cannot reach the verification server. Check that the backend '
                'is running and the API address is correct.'
            : 'The verification server failed to handle iris tracking '
                '(HTTP $statusCode).',
      );
    }
    final envelope = response.data is Map<String, dynamic>
        ? response.data as Map<String, dynamic>
        : const <String, dynamic>{};
    final data =
        (envelope['data'] as Map?)?.cast<String, dynamic>() ?? envelope;
    return IrisTrackingFrame.fromJson(data);
  }
}
