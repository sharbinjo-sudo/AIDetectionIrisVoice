import '../../test_mode/models/iris_test_result.dart';
import '../../test_mode/models/voice_test_result.dart';
import 'verification_result.dart';
import 'verification_step.dart';

class VerificationSession {
  const VerificationSession({
    required this.stage,
    required this.steps,
    this.faceImagePaths = const [],
    this.irisImagePaths = const [],
    this.irisImagePath,
    this.voiceFilePath,
    this.voiceFilePaths = const [],
    this.irisResult,
    this.voiceResult,
    this.finalResult,
    this.errorMessage,
    this.consentGiven = false,
  });

  final VerificationStage stage;
  final List<VerificationStep> steps;
  final List<String> faceImagePaths;
  final List<String> irisImagePaths;
  final String? irisImagePath;
  final String? voiceFilePath;
  final List<String> voiceFilePaths;
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
      'Face + iris samples',
      'Iris quality validation',
      'Speak challenge',
      'Speech clarity',
      'Identity confidence',
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
    List<String>? faceImagePaths,
    List<String>? irisImagePaths,
    Object? irisImagePath = _sentinel,
    Object? voiceFilePath = _sentinel,
    List<String>? voiceFilePaths,
    Object? irisResult = _sentinel,
    Object? voiceResult = _sentinel,
    Object? finalResult = _sentinel,
    Object? errorMessage = _sentinel,
    bool? consentGiven,
  }) {
    return VerificationSession(
      stage: stage ?? this.stage,
      steps: steps ?? this.steps,
      faceImagePaths: faceImagePaths ?? this.faceImagePaths,
      irisImagePaths: irisImagePaths ?? this.irisImagePaths,
      irisImagePath: identical(irisImagePath, _sentinel)
          ? this.irisImagePath
          : irisImagePath as String?,
      voiceFilePath: identical(voiceFilePath, _sentinel)
          ? this.voiceFilePath
          : voiceFilePath as String?,
      voiceFilePaths: voiceFilePaths ?? this.voiceFilePaths,
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
