class VoiceTestResult {
  const VoiceTestResult({
    required this.durationSeconds,
    required this.qualityScore,
    required this.speechDetected,
    required this.speechActivityScore,
    required this.rmsLevel,
    required this.peakLevel,
    required this.rawScore,
    required this.normalizedScore,
    required this.threshold,
    required this.passed,
    required this.processingTimeMs,
    required this.message,
  });

  final double? durationSeconds;
  final double? qualityScore;
  final bool speechDetected;
  final double? speechActivityScore;
  final double? rmsLevel;
  final double? peakLevel;
  final double? rawScore;
  final double? normalizedScore;
  final double? threshold;
  final bool passed;
  final int processingTimeMs;
  final String message;

  factory VoiceTestResult.fromJson(Map<String, dynamic> json) {
    final voice = (json['voice'] as Map?)?.cast<String, dynamic>() ?? json;
    return VoiceTestResult(
      durationSeconds: (voice['duration_seconds'] as num?)?.toDouble(),
      qualityScore: (voice['quality_score'] as num?)?.toDouble(),
      speechDetected: voice['speech_detected'] == true,
      speechActivityScore: (voice['speech_activity_score'] as num?)?.toDouble(),
      rmsLevel: (voice['rms_level'] as num?)?.toDouble(),
      peakLevel: (voice['peak_level'] as num?)?.toDouble(),
      rawScore: (voice['raw_score'] as num?)?.toDouble(),
      normalizedScore: (voice['normalized_score'] as num?)?.toDouble(),
      threshold: (voice['threshold'] as num?)?.toDouble(),
      passed: voice['passed'] == true,
      processingTimeMs:
          (json['processing_time_ms'] as num?)?.toInt() ??
          (voice['processing_time_ms'] as num?)?.toInt() ??
          0,
      message:
          json['message']?.toString() ??
          json['failure_reason']?.toString() ??
          voice['message']?.toString() ??
          '',
    );
  }
}
