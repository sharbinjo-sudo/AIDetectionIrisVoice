class BackendHealthStatus {
  const BackendHealthStatus({
    required this.connected,
    required this.databaseReady,
    required this.voiceModelReady,
    required this.irisModelReady,
    required this.faceModelReady,
    required this.voiceModelMode,
    required this.irisModelMode,
    required this.faceModelMode,
    required this.developmentThresholds,
  });

  final bool connected;
  final bool databaseReady;
  final bool voiceModelReady;
  final bool irisModelReady;
  final bool faceModelReady;
  final String voiceModelMode;
  final String irisModelMode;
  final String faceModelMode;
  final bool developmentThresholds;

  String get voiceModelLabel => _modelLabel(voiceModelMode);
  String get irisModelLabel => _modelLabel(irisModelMode);
  String get faceModelLabel => _modelLabel(faceModelMode);

  String _modelLabel(String mode) {
    if (mode == 'offline' || mode == 'unknown') return 'Unavailable';
    if (mode.startsWith('local_')) return 'Local deployed model';
    if (mode == 'heuristic') return 'Quality fallback';
    return 'Configured model';
  }

  /// True when the API/database answered, even if model warm-up is still in
  /// progress and the service is not ready for biometric capture yet.
  bool get reachable => connected || databaseReady;

  factory BackendHealthStatus.fromJson(Map<String, dynamic> json) {
    final voice =
        (json['voice_model'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final iris =
        (json['iris_model'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final face =
        (json['face_model'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return BackendHealthStatus(
      connected: json['status']?.toString() == 'ok',
      databaseReady: json['database']?.toString() == 'ready',
      voiceModelReady: voice['ready'] == true,
      irisModelReady: iris['ready'] == true,
      faceModelReady: face['ready'] == true,
      voiceModelMode: voice['mode']?.toString() ?? 'unknown',
      irisModelMode: iris['mode']?.toString() ?? 'unknown',
      faceModelMode: face['mode']?.toString() ?? 'unknown',
      developmentThresholds: json['development_thresholds'] == true,
    );
  }

  factory BackendHealthStatus.disconnected() {
    return const BackendHealthStatus(
      connected: false,
      databaseReady: false,
      voiceModelReady: false,
      irisModelReady: false,
      faceModelReady: false,
      voiceModelMode: 'offline',
      irisModelMode: 'offline',
      faceModelMode: 'offline',
      developmentThresholds: true,
    );
  }
}
