import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/core/errors/error_mapper.dart';
import 'package:frontend/features/irl_verification/models/verification_result.dart';
import 'package:frontend/features/irl_verification/models/verification_step.dart';
import 'package:frontend/features/irl_verification/providers/verification_controller.dart';

void main() {
  test('verification result parses backend fusion response correctly', () {
    final result = VerificationResult.fromJson({
      'face': {
        'raw_score': 0.84,
        'normalized_score': 0.92,
        'threshold': 0.70,
        'passed': true,
        'quality_score': 0.89,
        'sample_count': 3,
      },
      'voice': {
        'raw_score': 0.87,
        'normalized_score': 0.90,
        'threshold': 0.75,
        'passed': true,
        'quality_score': 0.88,
      },
      'iris': {
        'raw_score': 0.21,
        'normalized_score': 0.92,
        'threshold': 0.78,
        'passed': true,
        'quality_score': 0.91,
      },
      'fusion': {
        'face_weight': 0.34,
        'voice_weight': 0.50,
        'iris_weight': 0.50,
        'score': 0.91,
        'threshold': 0.80,
      },
      'decision': 'ACCEPTED',
      'failure_reason': null,
      'processing_time_ms': 1800,
      'attempt_id': 'attempt-123',
    });

    expect(result.accepted, isTrue);
    expect(result.processingError, isFalse);
    expect(result.voice.normalizedScore, 0.90);
    expect(result.face.normalizedScore, 0.92);
    expect(result.face.sampleCount, 3);
    expect(result.fusion.faceWeight, 0.34);
    expect(result.iris.normalizedScore, 0.92);
    expect(result.fusion.score, 0.91);
    expect(result.processingTimeMs, 1800);
    expect(result.attemptId, 'attempt-123');
  });

  test(
    'poor iris quality with strong voice parses as a retry, not a failure',
    () {
      final result = VerificationResult.fromJson({
        'voice': {
          'raw_score': 0.91,
          'normalized_score': 0.91,
          'threshold': 0.55,
          'passed': true,
          'quality_score': 0.91,
          'speech_detected': true,
          'speech_activity_score': 0.80,
          'valid_measurement': true,
          'reason_code': 'ALL_MODALITIES_VALID',
        },
        'iris': {
          'raw_score': 0.30,
          'normalized_score': 0.30,
          'threshold': 0.55,
          'passed': false,
          'quality_score': 0.30,
          'iris_detected': true,
          'detection_confidence': 1.0,
          'valid_measurement': false,
          'reason_code': 'IRIS_QUALITY_TOO_LOW',
        },
        'fusion': {
          'voice_weight': 1.0,
          'iris_weight': 0.0,
          'score': 0.0,
          'threshold': 0.66,
          'reason_code': 'IRIS_QUALITY_TOO_LOW',
        },
        'decision': 'RETRY_REQUIRED',
        'reason_code': 'IRIS_QUALITY_TOO_LOW',
        'reason_message': 'The iris capture is unclear.',
        'ui_state': 'QUALITY_TOO_LOW',
        'failure_reason': 'The iris capture is unclear.',
        'processing_time_ms': 1200,
      });

      expect(result.accepted, isFalse);
      expect(result.retryRequired, isTrue);
      expect(result.qualityTooLow, isTrue);
      expect(result.hasRejectionEvidence, isFalse);
      expect(stageForResult(result), VerificationStage.qualityTooLow);
    },
  );

  test('mismatch evidence maps to a rejection state', () {
    final result = VerificationResult.fromJson({
      'voice': {'normalized_score': 0.4, 'threshold': 0.55, 'passed': false},
      'iris': {'normalized_score': 0.4, 'threshold': 0.55, 'passed': false},
      'fusion': {
        'voice_weight': 0.5,
        'iris_weight': 0.5,
        'score': 0.4,
        'threshold': 0.66,
      },
      'decision': 'REJECTED_MISMATCH',
      'reason_code': 'REJECTED_MISMATCH',
      'ui_state': 'REJECTED_MISMATCH',
      'failure_reason': 'Biometric mismatch.',
      'processing_time_ms': 900,
    });

    expect(result.hasRejectionEvidence, isTrue);
    expect(stageForResult(result), VerificationStage.rejectedMismatch);
  });

  test('spoof evidence maps to the spoof rejection state', () {
    final result = VerificationResult.fromJson({
      'voice': {'normalized_score': 0.9, 'threshold': 0.55, 'passed': true},
      'iris': {'normalized_score': 0.9, 'threshold': 0.55, 'passed': true},
      'fusion': {
        'voice_weight': 0.5,
        'iris_weight': 0.5,
        'score': 0.9,
        'threshold': 0.66,
      },
      'decision': 'REJECTED_SPOOF',
      'reason_code': 'REJECTED_SPOOF',
      'ui_state': 'REJECTED_SPOOF',
      'processing_time_ms': 800,
    });

    expect(stageForResult(result), VerificationStage.rejectedSpoof);
  });

  test('verified ui_state maps to verified stage', () {
    final result = VerificationResult.fromJson({
      'voice': {'normalized_score': 0.9, 'threshold': 0.55, 'passed': true},
      'iris': {'normalized_score': 0.74, 'threshold': 0.55, 'passed': true},
      'fusion': {
        'voice_weight': 0.7,
        'iris_weight': 0.3,
        'score': 0.86,
        'threshold': 0.66,
      },
      'decision': 'ACCEPTED',
      'reason_code': 'ALL_MODALITIES_VALID',
      'ui_state': 'VERIFIED',
      'processing_time_ms': 1500,
    });

    expect(stageForResult(result), VerificationStage.verified);
  });

  test('error mapper reads backend validation envelope', () {
    final requestOptions = RequestOptions(path: '/test/voice/');
    final error = DioException(
      requestOptions: requestOptions,
      response: Response<Map<String, dynamic>>(
        requestOptions: requestOptions,
        statusCode: 400,
        data: {
          'message': 'voice_file: No file was submitted.',
          'errors': {
            'voice_file': ['No file was submitted.'],
          },
        },
      ),
    );

    final mapped = ErrorMapper.map(error);

    expect(mapped.message, contains('voice_file'));
    expect(mapped.code, '400');
  });
}
