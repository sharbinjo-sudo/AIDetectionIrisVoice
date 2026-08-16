import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/core/errors/error_mapper.dart';
import 'package:frontend/features/irl_verification/models/verification_result.dart';

void main() {
  test('verification result parses backend fusion response correctly', () {
    final result = VerificationResult.fromJson({
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
    expect(result.iris.normalizedScore, 0.92);
    expect(result.fusion.score, 0.91);
    expect(result.processingTimeMs, 1800);
    expect(result.attemptId, 'attempt-123');
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
