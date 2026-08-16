class AppConstants {
  const AppConstants._();

  static const double mobileBreakpoint = 600;
  static const double desktopBreakpoint = 1024;
  static const String verificationPhrase =
      'I am a real person and I am ready to verify.';
  static const String phaseOneNote =
      'This Phase 1 system performs privacy-first human verification with a '
      'blink challenge and spoken audio check. Advanced anti-spoofing and '
      'deepfake detection are planned for Phase 2.';
  static const String irlConsentNotice =
      'This verification sends temporary eye images and one voice recording to '
      'the connected local Django server for a human-check challenge. The app '
      'does not save completed verification attempts.';
  static const String testConsentNotice =
      'Test Mode uses temporary eye and voice samples for quality testing only. '
      'There is no registered-user comparison and the results are not saved.';
}
