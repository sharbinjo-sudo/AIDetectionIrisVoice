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
    required String userId,
    required List<String> facePaths,
    required List<String> irisPaths,
    required String voicePath,
    required String eyeSide,
    required String challengePhrase,
    ProgressCallback? onSendProgress,
  }) async {
    try {
      final form = FormData();
      form.fields
        ..add(MapEntry('user_id', userId))
        ..add(MapEntry('eye_side', eyeSide))
        ..add(MapEntry('challenge_phrase', challengePhrase));
      for (var index = 0; index < facePaths.length; index++) {
        form.files.add(
          MapEntry(
            'face_files',
            await _multipartFromPath(
              facePaths[index],
              filename: 'face_$index.jpg',
            ),
          ),
        );
      }
      for (var index = 0; index < irisPaths.length; index++) {
        form.files.add(
          MapEntry(
            'iris_files',
            await _multipartFromPath(
              irisPaths[index],
              filename: 'iris_$index.jpg',
            ),
          ),
        );
      }
      form.files.add(
        MapEntry(
          'voice_file',
          await _multipartFromPath(voicePath, filename: 'voice.wav'),
        ),
      );
      final response = await _dio.post<dynamic>(
        ApiEndpoints.biometricAuthenticate,
        data: form,
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

  Future<String> enrollBiometrics({
    required String userId,
    required List<String> facePaths,
    required List<String> irisPaths,
    required List<String> voicePaths,
    required String eyeSide,
  }) async {
    try {
      final form = FormData();
      form.fields.add(MapEntry('eye_side', eyeSide));
      for (var index = 0; index < facePaths.length; index++) {
        form.files.add(
          MapEntry(
            'face_files',
            await _multipartFromPath(
              facePaths[index],
              filename: 'face_$index.jpg',
            ),
          ),
        );
      }
      for (var index = 0; index < irisPaths.length; index++) {
        form.files.add(
          MapEntry(
            'iris_files',
            await _multipartFromPath(
              irisPaths[index],
              filename: 'iris_$index.jpg',
            ),
          ),
        );
      }
      for (var index = 0; index < voicePaths.length; index++) {
        form.files.add(
          MapEntry(
            'voice_files',
            await _multipartFromPath(
              voicePaths[index],
              filename: 'voice_$index.wav',
            ),
          ),
        );
      }
      final response = await _dio.post<dynamic>(
        ApiEndpoints.biometricEnrollment(userId),
        data: form,
      );
      final payload = response.data is Map<String, dynamic>
          ? response.data as Map<String, dynamic>
          : <String, dynamic>{};
      final data =
          (payload['data'] as Map?)?.cast<String, dynamic>() ?? payload;
      if (data['enrollment_status'] != 'COMPLETE') {
        throw StateError('Enrollment was not confirmed. Please try again.');
      }
      return data['message']?.toString() ??
          'Biometric enrollment completed successfully.';
    } catch (error) {
      throw ErrorMapper.map(error);
    }
  }

  Future<void> deleteTemporaryMedia(Iterable<String?> paths) async {
    await deleteLocalFilesIfExists(paths);
  }
}
