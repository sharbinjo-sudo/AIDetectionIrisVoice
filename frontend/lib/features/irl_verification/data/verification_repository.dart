import 'package:cross_file/cross_file.dart';
import 'package:dio/dio.dart';

import '../../../core/config/api_endpoints.dart';
import '../../../core/errors/error_mapper.dart';
import '../../../core/io/local_file_cleanup.dart';
import '../../test_mode/models/iris_test_result.dart';
import '../../test_mode/models/voice_test_result.dart';
import '../models/verification_result.dart';

class VerificationRepository {
  VerificationRepository(this._dio);

  final Dio _dio;

  Future<MultipartFile> _multipartFromPath(
    String path, {
    required String filename,
  }) async {
    final bytes = await XFile(path).readAsBytes();
    return MultipartFile.fromBytes(bytes, filename: filename);
  }

  Future<IrisTestResult> verifyIrisStep({
    required String imagePath,
    required String eyeSide,
  }) async {
    try {
      final response = await _dio.post<dynamic>(
        ApiEndpoints.testIris,
        data: FormData.fromMap({
          'image_file': await _multipartFromPath(
            imagePath,
            filename: 'open_eye.jpg',
          ),
          'eye_side': eyeSide,
          'mode': 'quality_only',
        }),
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

  Future<VoiceTestResult> verifyVoiceStep({required String voicePath}) async {
    try {
      final response = await _dio.post<dynamic>(
        ApiEndpoints.testVoice,
        data: FormData.fromMap({
          'voice_file': await _multipartFromPath(
            voicePath,
            filename: 'human_check.wav',
          ),
          'mode': 'quality_only',
        }),
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

  Future<VerificationResult> completeVerification({
    required String irisPath,
    required String blinkPath,
    required String voicePath,
    required String eyeSide,
    required String challengePhrase,
    ProgressCallback? onSendProgress,
  }) async {
    try {
      final response = await _dio.post<dynamic>(
        ApiEndpoints.biometricAuthenticate,
        data: FormData.fromMap({
          'iris_file': await _multipartFromPath(
            irisPath,
            filename: 'open_eye.jpg',
          ),
          'blink_file': await _multipartFromPath(
            blinkPath,
            filename: 'blink.jpg',
          ),
          'voice_file': await _multipartFromPath(
            voicePath,
            filename: 'human_check.wav',
          ),
          'eye_side': eyeSide,
          'challenge_phrase': challengePhrase,
        }),
        onSendProgress: onSendProgress,
      );
      final payload = response.data is Map<String, dynamic>
          ? response.data as Map<String, dynamic>
          : <String, dynamic>{};
      final data =
          (payload['data'] as Map?)?.cast<String, dynamic>() ?? payload;
      return VerificationResult.fromJson(data);
    } catch (error) {
      throw ErrorMapper.map(error);
    }
  }

  Future<void> deleteTemporaryMedia(Iterable<String?> paths) async {
    await deleteLocalFilesIfExists(paths);
  }
}
