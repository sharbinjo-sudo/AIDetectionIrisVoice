enum VerificationStage {
  idle,
  checkingPermissions,
  readyForIris,
  capturingIris,
  processingIris,
  irisPassed,
  readyForBlink,
  capturingBlink,
  processingBlink,
  blinkPassed,
  blinkFailed,
  irisFailed,
  readyForVoice,
  recordingVoice,
  processingVoice,
  voicePassed,
  voiceFailed,
  fusingScores,
  verified,
  rejected,
  processingError,
}

enum VerificationStepStatus {
  pending,
  processing,
  passed,
  failed,
  unavailable,
}

class VerificationStep {
  const VerificationStep({
    required this.label,
    required this.status,
  });

  final String label;
  final VerificationStepStatus status;

  VerificationStep copyWith({VerificationStepStatus? status}) {
    return VerificationStep(
      label: label,
      status: status ?? this.status,
    );
  }
}
