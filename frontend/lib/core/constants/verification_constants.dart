class VerificationConstants {
  const VerificationConstants._();

  // Two non-overlapping ECAPA segments are aggregated by the backend.
  static const int minVoiceSeconds = 4;
  static const int maxVoiceSeconds = 15;
  static const Duration voiceCountdown = Duration(seconds: 3);
  static const Duration statusTick = Duration(milliseconds: 700);
  static const List<String> irisProcessingStages = [
    'Uploading image',
    'Detecting eye',
    'Locating iris',
    'Checking image quality',
    'Generating iris template',
    'Calculating result',
  ];
  static const List<String> voiceProcessingStages = [
    'Uploading voice sample',
    'Checking audio duration',
    'Checking audio quality',
    'Extracting speaker embedding',
    'Comparing speaker identity',
    'Calculating result',
  ];
}
