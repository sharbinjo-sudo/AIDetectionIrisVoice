import '../../test_mode/models/iris_test_result.dart';
import '../../test_mode/models/voice_test_result.dart';
import 'verification_result.dart';
import 'verification_step.dart';

class VerificationSession {
  const VerificationSession({
    required this.stage,
    required this.steps,
    this.irisImagePath,
    this.blinkImagePath,
    this.voiceFilePath,
    this.irisResult,
    this.voiceResult,
    this.finalResult,
    this.errorMessage,
    this.consentGiven = false,
  });

  final VerificationStage stage;
  final List<VerificationStep> steps;
  final String? irisImagePath;
  final String? blinkImagePath;
  final String? voiceFilePath;
  final IrisTestResult? irisResult;
  final VoiceTestResult? voiceResult;
  final VerificationResult? finalResult;
  final String? errorMessage;
  final bool consentGiven;

  factory VerificationSession.initial() {
    const labels = [
      'Backend connection',
      'Camera permission',
      'Microphone permission',
      'Open-eye challenge',
      'Blink challenge',
      'Speak challenge',
      'Speech clarity',
      'Human confidence',
      'Final decision',
    ];
    return VerificationSession(
      stage: VerificationStage.idle,
      steps: labels
          .map(
            (label) => VerificationStep(
              label: label,
              status: VerificationStepStatus.pending,
            ),
          )
          .toList(),
    );
  }

  VerificationSession copyWith({
    VerificationStage? stage,
    List<VerificationStep>? steps,
    Object? irisImagePath = _sentinel,
    Object? blinkImagePath = _sentinel,
    Object? voiceFilePath = _sentinel,
    Object? irisResult = _sentinel,
    Object? voiceResult = _sentinel,
    Object? finalResult = _sentinel,
    Object? errorMessage = _sentinel,
    bool? consentGiven,
  }) {
    return VerificationSession(
      stage: stage ?? this.stage,
      steps: steps ?? this.steps,
      irisImagePath: identical(irisImagePath, _sentinel)
          ? this.irisImagePath
          : irisImagePath as String?,
      blinkImagePath: identical(blinkImagePath, _sentinel)
          ? this.blinkImagePath
          : blinkImagePath as String?,
      voiceFilePath: identical(voiceFilePath, _sentinel)
          ? this.voiceFilePath
          : voiceFilePath as String?,
      irisResult: identical(irisResult, _sentinel)
          ? this.irisResult
          : irisResult as IrisTestResult?,
      voiceResult: identical(voiceResult, _sentinel)
          ? this.voiceResult
          : voiceResult as VoiceTestResult?,
      finalResult: identical(finalResult, _sentinel)
          ? this.finalResult
          : finalResult as VerificationResult?,
      errorMessage: identical(errorMessage, _sentinel)
          ? this.errorMessage
          : errorMessage as String?,
      consentGiven: consentGiven ?? this.consentGiven,
    );
  }
}

const Object _sentinel = Object();
