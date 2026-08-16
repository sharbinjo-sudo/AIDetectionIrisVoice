class BackendHealthStatus {
  const BackendHealthStatus({
    required this.connected,
    required this.databaseReady,
    required this.voiceModelReady,
    required this.irisModelReady,
    required this.voiceModelMode,
    required this.irisModelMode,
    required this.developmentThresholds,
  });

  final bool connected;
  final bool databaseReady;
  final bool voiceModelReady;
  final bool irisModelReady;
  final String voiceModelMode;
  final String irisModelMode;
  final bool developmentThresholds;

  factory BackendHealthStatus.fromJson(Map<String, dynamic> json) {
    final voice = (json['voice_model'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final iris = (json['iris_model'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return BackendHealthStatus(
      connected: json['status']?.toString() == 'ok',
      databaseReady: json['database']?.toString() == 'ready',
      voiceModelReady: voice['ready'] == true,
      irisModelReady: iris['ready'] == true,
      voiceModelMode: voice['mode']?.toString() ?? 'unknown',
      irisModelMode: iris['mode']?.toString() ?? 'unknown',
      developmentThresholds: json['development_thresholds'] == true,
    );
  }

  factory BackendHealthStatus.disconnected() {
    return const BackendHealthStatus(
      connected: false,
      databaseReady: false,
      voiceModelReady: false,
      irisModelReady: false,
      voiceModelMode: 'offline',
      irisModelMode: 'offline',
      developmentThresholds: true,
    );
  }
}
