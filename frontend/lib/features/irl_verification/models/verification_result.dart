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
  });

  final double? rawScore;
  final double normalizedScore;
  final double threshold;
  final bool passed;
  final double? qualityScore;
  final double? speechActivityScore;
  final double? activityThreshold;
  final bool? speechDetected;

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
    );
  }
}

class FusionMetric {
  const FusionMetric({
    required this.voiceWeight,
    required this.irisWeight,
    required this.score,
    required this.threshold,
  });

  final double voiceWeight;
  final double irisWeight;
  final double score;
  final double threshold;

  factory FusionMetric.fromJson(Map<String, dynamic> json) {
    return FusionMetric(
      voiceWeight: (json['voice_weight'] as num?)?.toDouble() ?? 0.5,
      irisWeight: (json['iris_weight'] as num?)?.toDouble() ?? 0.5,
      score: (json['score'] as num?)?.toDouble() ?? 0,
      threshold: (json['threshold'] as num?)?.toDouble() ?? 0,
    );
  }
}

class VerificationResult {
  const VerificationResult({
    required this.voice,
    required this.iris,
    required this.fusion,
    required this.decision,
    required this.failureReason,
    required this.processingTimeMs,
    this.attemptId,
  });

  final VerificationMetric voice;
  final VerificationMetric iris;
  final FusionMetric fusion;
  final String decision;
  final String? failureReason;
  final int processingTimeMs;
  final String? attemptId;

  bool get accepted => decision == 'ACCEPTED';
  bool get processingError => decision == 'PROCESSING_ERROR';

  factory VerificationResult.fromJson(Map<String, dynamic> json) {
    return VerificationResult(
      voice: VerificationMetric.fromJson(
        (json['voice'] as Map?)?.cast<String, dynamic>() ??
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
    );
  }
}
