import 'package:dio/dio.dart';
import 'package:cross_file/cross_file.dart';

import '../../../core/config/api_endpoints.dart';
import '../../../core/errors/error_mapper.dart';
import '../models/iris_test_result.dart';
import '../models/voice_test_result.dart';

class TestRepository {
  TestRepository(this._dio);

  final Dio _dio;

  Future<MultipartFile> _multipartFromPath(
    String path, {
    required String filename,
  }) async {
    final bytes = await XFile(path).readAsBytes();
    return MultipartFile.fromBytes(bytes, filename: filename);
  }

  Future<IrisTestResult> analyzeIris({
    required String imagePath,
    required String eyeSide,
    ProgressCallback? onSendProgress,
  }) async {
    try {
      final response = await _dio.post<dynamic>(
        ApiEndpoints.testIris,
        data: FormData.fromMap({
          'image_file': await _multipartFromPath(
            imagePath,
            filename: 'eye_capture.jpg',
          ),
          'eye_side': eyeSide,
          'mode': 'quality_only',
        }),
        onSendProgress: onSendProgress,
      );
      final payload = response.data is Map<String, dynamic>
          ? response.data as Map<String, dynamic>
          : <String, dynamic>{};
      final data =
          (payload['data'] as Map?)?.cast<String, dynamic>() ?? payload;
      return IrisTestResult.fromJson(data);
    } catch (error) {
      throw ErrorMapper.map(error);
    }
  }

  Future<VoiceTestResult> analyzeVoice({
    required String audioPath,
    ProgressCallback? onSendProgress,
  }) async {
    try {
      final response = await _dio.post<dynamic>(
        ApiEndpoints.testVoice,
        data: FormData.fromMap({
          'voice_file': await _multipartFromPath(
            audioPath,
            filename: 'voice_sample.wav',
          ),
          'mode': 'quality_only',
        }),
        onSendProgress: onSendProgress,
      );
      final payload = response.data is Map<String, dynamic>
          ? response.data as Map<String, dynamic>
          : <String, dynamic>{};
      final data =
          (payload['data'] as Map?)?.cast<String, dynamic>() ?? payload;
      return VoiceTestResult.fromJson(data);
    } catch (error) {
      throw ErrorMapper.map(error);
    }
  }
}
