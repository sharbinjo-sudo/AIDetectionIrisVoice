enum EnrollmentStatus {
  notStarted('NOT_STARTED', 'Not started'),
  voicePending('VOICE_PENDING', 'Voice pending'),
  irisPending('IRIS_PENDING', 'Iris pending'),
  complete('COMPLETE', 'Complete');

  const EnrollmentStatus(this.apiValue, this.label);

  final String apiValue;
  final String label;

  static EnrollmentStatus fromApi(String? value) {
    return EnrollmentStatus.values.firstWhere(
      (status) => status.apiValue == value,
      orElse: () => EnrollmentStatus.notStarted,
    );
  }
}

enum AuthenticationDecision {
  accepted('ACCEPTED', 'Accepted'),
  rejected('REJECTED', 'Rejected'),
  processingError('PROCESSING_ERROR', 'Processing error');

  const AuthenticationDecision(this.apiValue, this.label);

  final String apiValue;
  final String label;

  static AuthenticationDecision fromApi(String? value) {
    return AuthenticationDecision.values.firstWhere(
      (decision) => decision.apiValue == value,
      orElse: () => AuthenticationDecision.processingError,
    );
  }
}

class AuthSession {
  const AuthSession({
    required this.accessToken,
    required this.refreshToken,
    required this.username,
  });

  final String accessToken;
  final String refreshToken;
  final String username;
}

class BiometricUser {
  const BiometricUser({
    required this.id,
    required this.externalId,
    required this.fullName,
    required this.email,
    required this.phone,
    required this.isActive,
    required this.enrollmentStatus,
  });

  final String id;
  final String externalId;
  final String fullName;
  final String email;
  final String phone;
  final bool isActive;
  final EnrollmentStatus enrollmentStatus;

  factory BiometricUser.fromJson(Map<String, dynamic> json) {
    return BiometricUser(
      id: json['id']?.toString() ?? '',
      externalId: json['external_id']?.toString() ?? '',
      fullName: json['full_name']?.toString() ?? '',
      email: json['email']?.toString() ?? '',
      phone: json['phone']?.toString() ?? '',
      isActive: json['is_active'] == true,
      enrollmentStatus: EnrollmentStatus.fromApi(
        json['enrollment_status']?.toString(),
      ),
    );
  }

  Map<String, dynamic> toCreateJson() {
    return {
      'external_id': externalId,
      'full_name': fullName,
      'email': email,
      'phone': phone,
    };
  }
}

class EnrollmentProgress {
  const EnrollmentProgress({
    required this.userId,
    required this.status,
    required this.voiceSamples,
    required this.irisSamples,
    required this.eyeSide,
    required this.consentAccepted,
  });

  final String userId;
  final EnrollmentStatus status;
  final int voiceSamples;
  final int irisSamples;
  final String eyeSide;
  final bool consentAccepted;

  factory EnrollmentProgress.empty(String userId) {
    return EnrollmentProgress(
      userId: userId,
      status: EnrollmentStatus.notStarted,
      voiceSamples: 0,
      irisSamples: 0,
      eyeSide: 'LEFT',
      consentAccepted: false,
    );
  }

  EnrollmentProgress copyWith({
    EnrollmentStatus? status,
    int? voiceSamples,
    int? irisSamples,
    String? eyeSide,
    bool? consentAccepted,
  }) {
    return EnrollmentProgress(
      userId: userId,
      status: status ?? this.status,
      voiceSamples: voiceSamples ?? this.voiceSamples,
      irisSamples: irisSamples ?? this.irisSamples,
      eyeSide: eyeSide ?? this.eyeSide,
      consentAccepted: consentAccepted ?? this.consentAccepted,
    );
  }
}

class AuthenticationAttempt {
  const AuthenticationAttempt({
    required this.id,
    required this.userName,
    required this.decision,
    required this.createdAt,
    required this.voiceScore,
    required this.irisScore,
    required this.fusedScore,
    required this.failureReason,
  });

  final String id;
  final String userName;
  final AuthenticationDecision decision;
  final DateTime createdAt;
  final double? voiceScore;
  final double? irisScore;
  final double? fusedScore;
  final String failureReason;

  factory AuthenticationAttempt.fromJson(Map<String, dynamic> json) {
    return AuthenticationAttempt(
      id: json['id']?.toString() ?? '',
      userName:
          json['claimed_user_name']?.toString() ??
          json['claimed_user']?.toString() ??
          'Unknown',
      decision: AuthenticationDecision.fromApi(
        json['final_decision']?.toString(),
      ),
      createdAt:
          DateTime.tryParse(json['created_at']?.toString() ?? '') ??
          DateTime.fromMillisecondsSinceEpoch(0),
      voiceScore: (json['voice_normalized_score'] as num?)?.toDouble(),
      irisScore: (json['iris_normalized_score'] as num?)?.toDouble(),
      fusedScore: (json['fused_score'] as num?)?.toDouble(),
      failureReason: json['failure_reason']?.toString() ?? '',
    );
  }
}

class BiometricAuthResult {
  const BiometricAuthResult({
    required this.decision,
    required this.voiceScore,
    required this.irisScore,
    required this.fusedScore,
    required this.voiceThreshold,
    required this.irisThreshold,
    required this.fusionThreshold,
    required this.processingTimeMs,
    required this.failureReason,
  });

  final AuthenticationDecision decision;
  final double voiceScore;
  final double irisScore;
  final double fusedScore;
  final double voiceThreshold;
  final double irisThreshold;
  final double fusionThreshold;
  final int processingTimeMs;
  final String failureReason;

  factory BiometricAuthResult.fromJson(Map<String, dynamic> json) {
    return BiometricAuthResult(
      decision: AuthenticationDecision.fromApi(
        json['final_decision']?.toString(),
      ),
      voiceScore: (json['voice_normalized_score'] as num?)?.toDouble() ?? 0,
      irisScore: (json['iris_normalized_score'] as num?)?.toDouble() ?? 0,
      fusedScore: (json['fused_score'] as num?)?.toDouble() ?? 0,
      voiceThreshold: (json['voice_threshold'] as num?)?.toDouble() ?? 0.55,
      irisThreshold: (json['iris_threshold'] as num?)?.toDouble() ?? 0.55,
      fusionThreshold: (json['fusion_threshold'] as num?)?.toDouble() ?? 0.80,
      processingTimeMs: (json['processing_time_ms'] as num?)?.toInt() ?? 0,
      failureReason: json['failure_reason']?.toString() ?? '',
    );
  }
}

class HealthStatus {
  const HealthStatus({
    required this.status,
    required this.databaseReady,
    required this.voiceModelReady,
    required this.irisModelReady,
    required this.developmentThresholds,
  });

  final String status;
  final bool databaseReady;
  final bool voiceModelReady;
  final bool irisModelReady;
  final bool developmentThresholds;

  factory HealthStatus.fromJson(Map<String, dynamic> json) {
    final voiceModel =
        (json['voice_model'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final irisModel =
        (json['iris_model'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};

    return HealthStatus(
      status: json['status']?.toString() ?? 'unknown',
      databaseReady: json['database']?.toString() == 'ready',
      voiceModelReady: voiceModel['ready'] == true,
      irisModelReady: irisModel['ready'] == true,
      developmentThresholds: json['development_thresholds'] == true,
    );
  }

  factory HealthStatus.unreachable() {
    return const HealthStatus(
      status: 'offline',
      databaseReady: false,
      voiceModelReady: false,
      irisModelReady: false,
      developmentThresholds: true,
    );
  }
}

class SystemConfiguration {
  const SystemConfiguration({
    required this.voiceWeight,
    required this.irisWeight,
    required this.voiceThreshold,
    required this.irisThreshold,
    required this.fusionThreshold,
    required this.minimumVoiceSamples,
    required this.minimumIrisSamples,
  });

  final double voiceWeight;
  final double irisWeight;
  final double voiceThreshold;
  final double irisThreshold;
  final double fusionThreshold;
  final int minimumVoiceSamples;
  final int minimumIrisSamples;

  factory SystemConfiguration.development() {
    return const SystemConfiguration(
      voiceWeight: 0.5,
      irisWeight: 0.5,
      voiceThreshold: 0.55,
      irisThreshold: 0.55,
      fusionThreshold: 0.80,
      minimumVoiceSamples: 1,
      minimumIrisSamples: 1,
    );
  }

  factory SystemConfiguration.fromJson(Map<String, dynamic> json) {
    return SystemConfiguration(
      voiceWeight: (json['voice_weight'] as num?)?.toDouble() ?? 0.5,
      irisWeight: (json['iris_weight'] as num?)?.toDouble() ?? 0.5,
      voiceThreshold: (json['voice_threshold'] as num?)?.toDouble() ?? 0.55,
      irisThreshold: (json['iris_threshold'] as num?)?.toDouble() ?? 0.55,
      fusionThreshold: (json['fusion_threshold'] as num?)?.toDouble() ?? 0.80,
      minimumVoiceSamples:
          (json['minimum_voice_samples'] as num?)?.toInt() ?? 1,
      minimumIrisSamples: (json['minimum_iris_samples'] as num?)?.toInt() ?? 1,
    );
  }
}

dynamic unwrapApiData(dynamic payload) {
  if (payload is Map<String, dynamic> && payload['data'] != null) {
    return payload['data'];
  }
  return payload;
}

List<Map<String, dynamic>> unwrapApiList(dynamic payload) {
  final data = unwrapApiData(payload);
  if (data is List) {
    return data
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .toList();
  }
  if (data is Map<String, dynamic> && data['results'] is List) {
    return (data['results'] as List)
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .toList();
  }
  return const [];
}
