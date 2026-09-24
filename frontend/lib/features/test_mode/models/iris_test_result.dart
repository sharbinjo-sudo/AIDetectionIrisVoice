class IrisTestResult {
  const IrisTestResult({
    required this.irisDetected,
    required this.qualityScore,
    required this.rawScore,
    required this.normalizedScore,
    required this.threshold,
    required this.passed,
    required this.processingTimeMs,
    required this.message,
  });

  final bool irisDetected;
  final double? qualityScore;
  final double? rawScore;
  final double? normalizedScore;
  final double? threshold;
  final bool passed;
  final int processingTimeMs;
  final String message;

  factory IrisTestResult.fromJson(Map<String, dynamic> json) {
    final iris = (json['iris'] as Map?)?.cast<String, dynamic>() ?? json;
    return IrisTestResult(
      irisDetected: iris['iris_detected'] == true || iris['passed'] == true,
      qualityScore: (iris['quality_score'] as num?)?.toDouble(),
      rawScore: (iris['raw_score'] as num?)?.toDouble(),
      normalizedScore: (iris['normalized_score'] as num?)?.toDouble(),
      threshold: (iris['threshold'] as num?)?.toDouble(),
      passed: iris['passed'] == true,
      processingTimeMs:
          (json['processing_time_ms'] as num?)?.toInt() ??
          (iris['processing_time_ms'] as num?)?.toInt() ??
          0,
      message:
          json['message']?.toString() ??
          json['failure_reason']?.toString() ??
          iris['message']?.toString() ??
          '',
    );
  }
}
