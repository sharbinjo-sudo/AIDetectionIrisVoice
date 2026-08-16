class ApiEndpoints {
  const ApiEndpoints._();

  static const String health = '/health/';
  static const String users = '/users/';
  static const String testIris = '/test/iris/';
  static const String testVoice = '/test/voice/';
  static const String biometricAuthenticate = '/biometric-authenticate/';
  static const String configuration = '/system/configuration/';

  static String userDetail(String userId) => '/users/$userId/';
  static String enrollmentStatus(String userId) =>
      '/users/$userId/enrollment/status/';
  static String saveAttempt(String attemptId) =>
      '/authentication-attempts/$attemptId/save/';
}
