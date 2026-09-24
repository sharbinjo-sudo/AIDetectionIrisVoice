enum VerificationStage {
  idle,
  checkingPermissions,
  readyForFace,
  capturingFace,
  faceFailed,
  readyForIris,
  capturingIris,
  processingIris,
  irisPassed,
  irisFailed,
  readyForVoice,
  recordingVoice,
  processingVoice,
  voicePassed,
  voiceFailed,
  fusingScores,
  qualityTooLow,
  retryRequired,
  verification,
  verified,
  rejectedSpoof,
  rejectedMismatch,
  rejected,
  processingError,
}

enum VerificationStepStatus { pending, processing, passed, failed, unavailable }

class VerificationStep {
  const VerificationStep({required this.label, required this.status});

  final String label;
  final VerificationStepStatus status;

  VerificationStep copyWith({VerificationStepStatus? status}) {
    return VerificationStep(label: label, status: status ?? this.status);
  }
}
