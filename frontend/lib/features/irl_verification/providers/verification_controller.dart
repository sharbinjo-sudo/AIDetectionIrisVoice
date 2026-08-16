import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:permission_handler/permission_handler.dart';

import '../../../core/constants/app_constants.dart';
import '../../../core/networking/dio_client.dart';
import '../data/verification_repository.dart';
import '../models/verification_result.dart';
import '../models/verification_session.dart';
import '../models/verification_step.dart';

final verificationRepositoryProvider = Provider<VerificationRepository>(
  (ref) => VerificationRepository(ref.watch(dioProvider)),
);

class VerificationController extends Notifier<VerificationSession> {
  @override
  VerificationSession build() => VerificationSession.initial();

  VerificationRepository get _repository =>
      ref.read(verificationRepositoryProvider);

  void setConsent(bool value) {
    state = state.copyWith(consentGiven: value, errorMessage: null);
  }

  Future<void> startHumanCheck({
    required bool backendConnected,
  }) async {
    if (!state.consentGiven) {
      state = state.copyWith(
        stage: VerificationStage.processingError,
        errorMessage: 'Tick "I am not a robot" to begin the verification flow.',
      );
      return;
    }

    _setStep(
      0,
      backendConnected
          ? VerificationStepStatus.passed
          : VerificationStepStatus.failed,
    );

    if (!backendConnected) {
      state = state.copyWith(
        stage: VerificationStage.processingError,
        errorMessage:
            'Cannot reach the verification server. Check that Django is running and that the API address is correct.',
      );
      return;
    }

    await checkPermissions();
  }

  void setOpenEyeImage(String path) {
    state = state.copyWith(
      irisImagePath: path,
      stage: VerificationStage.capturingIris,
      errorMessage: null,
    );
  }

  void clearOpenEyeImage() {
    state = state.copyWith(
      irisImagePath: null,
      irisResult: null,
      errorMessage: null,
      stage: VerificationStage.readyForIris,
    );
  }

  void setBlinkImage(String path) {
    state = state.copyWith(
      blinkImagePath: path,
      stage: VerificationStage.capturingBlink,
      errorMessage: null,
    );
  }

  void clearBlinkImage() {
    state = state.copyWith(
      blinkImagePath: null,
      errorMessage: null,
      stage: VerificationStage.readyForBlink,
    );
  }

  void advanceToVoiceAfterBlink() {
    _setStep(4, VerificationStepStatus.processing);
    state = state.copyWith(
      stage: VerificationStage.readyForVoice,
      errorMessage: null,
    );
  }

  void setVoiceFile(String path) {
    state = state.copyWith(
      voiceFilePath: path,
      stage: VerificationStage.recordingVoice,
      errorMessage: null,
    );
  }

  void clearVoiceFile() {
    state = state.copyWith(
      voiceFilePath: null,
      voiceResult: null,
      errorMessage: null,
      stage: VerificationStage.readyForVoice,
    );
  }

  Future<void> checkPermissions() async {
    state = state.copyWith(stage: VerificationStage.checkingPermissions);
    final cameraGranted = (await Permission.camera.request()).isGranted;
    final micGranted = (await Permission.microphone.request()).isGranted;
    final steps = [...state.steps];
    steps[1] = steps[1].copyWith(
      status: cameraGranted
          ? VerificationStepStatus.passed
          : VerificationStepStatus.failed,
    );
    steps[2] = steps[2].copyWith(
      status:
          micGranted ? VerificationStepStatus.passed : VerificationStepStatus.failed,
    );
    state = state.copyWith(
      steps: steps,
      stage: cameraGranted && micGranted
          ? VerificationStage.readyForIris
          : VerificationStage.processingError,
      errorMessage: cameraGranted && micGranted
          ? null
          : 'Camera and microphone access are required for human verification.',
    );
  }

  Future<void> verifyIrisStep({String eyeSide = 'LEFT'}) async {
    if (state.irisImagePath == null || state.irisImagePath!.isEmpty) {
      state = state.copyWith(
        stage: VerificationStage.irisFailed,
        errorMessage: 'Capture an open-eye image first.',
      );
      return;
    }
    _setStep(3, VerificationStepStatus.processing);
    state = state.copyWith(stage: VerificationStage.processingIris);
    try {
      final result = await _repository.verifyIrisStep(
        imagePath: state.irisImagePath!,
        eyeSide: eyeSide,
      );
      _setStep(
        3,
        result.passed
            ? VerificationStepStatus.passed
            : VerificationStepStatus.failed,
      );
      state = state.copyWith(
        irisResult: result,
        stage:
            result.passed ? VerificationStage.readyForBlink : VerificationStage.irisFailed,
        errorMessage: result.passed ? null : result.message,
      );
    } catch (error) {
      _setStep(3, VerificationStepStatus.failed);
      state = state.copyWith(
        stage: VerificationStage.irisFailed,
        errorMessage: error.toString(),
      );
    }
  }

  Future<void> verifyVoiceStep() async {
    if (state.voiceFilePath == null || state.voiceFilePath!.isEmpty) {
      state = state.copyWith(
        stage: VerificationStage.voiceFailed,
        errorMessage: 'Capture a spoken response first.',
      );
      return;
    }
    _setStep(5, VerificationStepStatus.passed);
    _setStep(6, VerificationStepStatus.processing);
    state = state.copyWith(stage: VerificationStage.processingVoice);
    try {
      final result = await _repository.verifyVoiceStep(
        voicePath: state.voiceFilePath!,
      );
      _setStep(
        6,
        result.passed
            ? VerificationStepStatus.passed
            : VerificationStepStatus.failed,
      );
      state = state.copyWith(
        voiceResult: result,
        stage:
            result.passed ? VerificationStage.fusingScores : VerificationStage.voiceFailed,
        errorMessage: result.passed ? null : result.message,
      );
    } catch (error) {
      _setStep(6, VerificationStepStatus.failed);
      state = state.copyWith(
        stage: VerificationStage.voiceFailed,
        errorMessage: error.toString(),
      );
    }
  }

  Future<VerificationResult?> finalize({String eyeSide = 'LEFT'}) async {
    if (state.irisImagePath == null ||
        state.blinkImagePath == null ||
        state.voiceFilePath == null) {
      state = state.copyWith(
        stage: VerificationStage.processingError,
        errorMessage:
            'Open-eye, blink, and spoken-response media are required before final verification.',
      );
      return null;
    }

    _setStep(4, VerificationStepStatus.processing);
    _setStep(7, VerificationStepStatus.processing);
    _setStep(8, VerificationStepStatus.processing);
    state = state.copyWith(stage: VerificationStage.fusingScores);

    try {
      final result = await _repository.completeVerification(
        irisPath: state.irisImagePath!,
        blinkPath: state.blinkImagePath!,
        voicePath: state.voiceFilePath!,
        eyeSide: eyeSide,
        challengePhrase: AppConstants.verificationPhrase,
      );
      _setStep(
        4,
        result.iris.passed
            ? VerificationStepStatus.passed
            : VerificationStepStatus.failed,
      );
      _setStep(
        7,
        result.fusion.score >= result.fusion.threshold
            ? VerificationStepStatus.passed
            : VerificationStepStatus.failed,
      );
      _setStep(
        8,
        result.accepted
            ? VerificationStepStatus.passed
            : VerificationStepStatus.failed,
      );
      state = state.copyWith(
        finalResult: result,
        stage: result.processingError
            ? VerificationStage.processingError
            : result.accepted
                ? VerificationStage.verified
                : VerificationStage.rejected,
        errorMessage: result.failureReason,
      );
      return result;
    } catch (error) {
      _setStep(4, VerificationStepStatus.failed);
      _setStep(7, VerificationStepStatus.failed);
      _setStep(8, VerificationStepStatus.failed);
      state = state.copyWith(
        stage: VerificationStage.processingError,
        errorMessage: error.toString(),
      );
      return null;
    }
  }

  Future<void> cleanup() async {
    await _repository.deleteTemporaryMedia([
      state.irisImagePath,
      state.blinkImagePath,
      state.voiceFilePath,
    ]);
  }

  void restart() {
    state = VerificationSession.initial();
  }

  void _setStep(int index, VerificationStepStatus status) {
    final steps = [...state.steps];
    steps[index] = steps[index].copyWith(status: status);
    state = state.copyWith(steps: steps);
  }
}

final verificationProvider =
    NotifierProvider<VerificationController, VerificationSession>(
  VerificationController.new,
);
