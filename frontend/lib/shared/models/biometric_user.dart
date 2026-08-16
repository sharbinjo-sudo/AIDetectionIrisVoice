class BiometricUser {
  const BiometricUser({
    required this.id,
    required this.externalId,
    required this.fullName,
    required this.enrollmentStatus,
  });

  final String id;
  final String externalId;
  final String fullName;
  final String enrollmentStatus;

  factory BiometricUser.fromJson(Map<String, dynamic> json) {
    return BiometricUser(
      id: json['id']?.toString() ?? '',
      externalId: json['external_id']?.toString() ?? '',
      fullName: json['full_name']?.toString() ?? '',
      enrollmentStatus: json['enrollment_status']?.toString() ?? 'UNKNOWN',
    );
  }
}
