class AppConstants {
  const AppConstants._();

  static const String appTitle =
      'Advanced Human Recognition Using AI and Multibiometric Authentication';

  static const double mobileBreakpoint = 600;
  static const double navigationBreakpoint = 1050;
  static const double desktopBreakpoint = 1024;
  static const String verificationPhrase =
      'I am a real person and I am ready to verify.';
  static const String irlConsentNotice =
      'This verification sends temporary face and eye images plus one voice recording to '
      'the connected local Django server. Registration stores derived biometric '
      'templates; login captures are deleted after comparison. Diagnostic scores '
      'and decisions may be retained locally for security auditing.';
  static const String testConsentNotice =
      'Test Mode uses temporary eye and voice samples for quality testing only. '
      'There is no registered-user comparison and the results are not saved.';
}
