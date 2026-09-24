class VerificationMetric {
  const VerificationMetric({
    required this.rawScore,
    required this.normalizedScore,
    required this.threshold,
    required this.passed,
    this.qualityScore,
    this.speechActivityScore,
    this.activityThreshold,
    this.speechDetected,
    this.irisDetected,
    this.detectionConfidence,
    this.similarityScore,
    this.validMeasurement,
    this.reasonCode,
    this.qualityThreshold,
    this.sampleCount,
    this.message,
  });

  final double? rawScore;
  final double normalizedScore;
  final double threshold;
  final bool passed;
  final double? qualityScore;
  final double? speechActivityScore;
  final double? activityThreshold;
  final bool? speechDetected;
  final bool? irisDetected;
  final double? detectionConfidence;
  final double? similarityScore;
  final bool? validMeasurement;
  final String? reasonCode;
  final double? qualityThreshold;
  final int? sampleCount;
  final String? message;

  factory VerificationMetric.fromJson(Map<String, dynamic> json) {
    return VerificationMetric(
      rawScore: (json['raw_score'] as num?)?.toDouble(),
      normalizedScore: (json['normalized_score'] as num?)?.toDouble() ?? 0,
      threshold: (json['threshold'] as num?)?.toDouble() ?? 0,
      passed: json['passed'] == true,
      qualityScore: (json['quality_score'] as num?)?.toDouble(),
      speechActivityScore: (json['speech_activity_score'] as num?)?.toDouble(),
      activityThreshold: (json['activity_threshold'] as num?)?.toDouble(),
      speechDetected: json['speech_detected'] is bool
          ? json['speech_detected'] as bool
          : null,
      irisDetected: json['iris_detected'] as bool?,
      detectionConfidence: (json['detection_confidence'] as num?)?.toDouble(),
      similarityScore: (json['similarity_score'] as num?)?.toDouble(),
      validMeasurement: json['valid_measurement'] as bool?,
      reasonCode: json['reason_code']?.toString(),
      qualityThreshold: (json['quality_threshold'] as num?)?.toDouble(),
      sampleCount: (json['sample_count'] as num?)?.toInt(),
      message: json['message']?.toString(),
    );
  }
}

class FusionMetric {
  const FusionMetric({
    required this.voiceWeight,
    required this.irisWeight,
    this.faceWeight = 0,
    required this.score,
    required this.threshold,
    this.reasonCode,
    this.voiceNormalizedScore,
    this.irisNormalizedScore,
    this.faceNormalizedScore,
  });

  final double voiceWeight;
  final double irisWeight;
  final double faceWeight;
  final double score;
  final double threshold;
  final String? reasonCode;
  final double? voiceNormalizedScore;
  final double? irisNormalizedScore;
  final double? faceNormalizedScore;

  factory FusionMetric.fromJson(Map<String, dynamic> json) {
    return FusionMetric(
      voiceWeight: (json['voice_weight'] as num?)?.toDouble() ?? 0.5,
      irisWeight: (json['iris_weight'] as num?)?.toDouble() ?? 0.5,
      faceWeight: (json['face_weight'] as num?)?.toDouble() ?? 0,
      score: (json['score'] as num?)?.toDouble() ?? 0,
      threshold: (json['threshold'] as num?)?.toDouble() ?? 0,
      reasonCode: json['reason_code']?.toString(),
      voiceNormalizedScore: (json['voice_normalized_score'] as num?)
          ?.toDouble(),
      irisNormalizedScore: (json['iris_normalized_score'] as num?)?.toDouble(),
      faceNormalizedScore: (json['face_normalized_score'] as num?)?.toDouble(),
    );
  }
}

class VerificationResult {
  const VerificationResult({
    required this.voice,
    required this.iris,
    required this.face,
    required this.fusion,
    required this.decision,
    required this.failureReason,
    required this.processingTimeMs,
    this.attemptId,
    this.reasonCode,
    this.reasonMessage,
    this.uiState,
  });

  final VerificationMetric voice;
  final VerificationMetric iris;
  final VerificationMetric face;
  final FusionMetric fusion;
  final String decision;
  final String? failureReason;
  final int processingTimeMs;
  final String? attemptId;
  final String? reasonCode;
  final String? reasonMessage;
  final String? uiState;

  bool get accepted => decision == 'ACCEPTED';
  bool get retryRequired => decision == 'RETRY_REQUIRED';
  bool get processingError => decision == 'PROCESSING_ERROR';

  /// Only explicit evidence of mismatch or spoofing justifies calling a
  /// result "failed" in the UI. Poor capture quality is a retry, not a
  /// biometric failure.
  bool get rejectedMismatch =>
      decision == 'REJECTED_MISMATCH' || uiState == 'REJECTED_MISMATCH';
  bool get rejectedSpoof =>
      decision == 'REJECTED_SPOOF' || uiState == 'REJECTED_SPOOF';
  bool get hasRejectionEvidence => rejectedMismatch || rejectedSpoof;
  bool get qualityTooLow =>
      retryRequired && (uiState == 'QUALITY_TOO_LOW' || _isQualityReason);

  factory VerificationResult.fromJson(Map<String, dynamic> json) {
    return VerificationResult(
      voice: VerificationMetric.fromJson(
        (json['voice'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{},
      ),
      face: VerificationMetric.fromJson(
        (json['face'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{},
      ),
      iris: VerificationMetric.fromJson(
        (json['iris'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{},
      ),
      fusion: FusionMetric.fromJson(
        (json['fusion'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{},
      ),
      decision: json['decision']?.toString() ?? 'PROCESSING_ERROR',
      failureReason: json['failure_reason']?.toString(),
      processingTimeMs: (json['processing_time_ms'] as num?)?.toInt() ?? 0,
      attemptId: json['attempt_id']?.toString(),
      reasonCode: json['reason_code']?.toString(),
      reasonMessage: json['reason_message']?.toString(),
      uiState: json['ui_state']?.toString(),
    );
  }

  static const _qualityReasons = {
    'IRIS_NOT_DETECTED',
    'IRIS_QUALITY_TOO_LOW',
    'VOICE_QUALITY_TOO_LOW',
    'VOICE_NO_SPEECH_ACTIVITY',
    'NO_VALID_MODALITY',
  };

  bool get _isQualityReason =>
      (uiState == 'QUALITY_TOO_LOW') ||
      (reasonCode != null && _qualityReasons.contains(reasonCode));
}
