import 'dart:async';

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

/// Maps a backend decision payload onto the UI's explicit verification
/// states. Rejections require actual mismatch/spoof evidence; capture
/// quality problems map to retry states instead.
VerificationStage stageForResult(VerificationResult result) {
  if (result.processingError) {
    return VerificationStage.processingError;
  }
  switch (result.uiState) {
    case 'VERIFIED':
      return VerificationStage.verified;
    case 'REJECTED_SPOOF':
      return VerificationStage.rejectedSpoof;
    case 'REJECTED_MISMATCH':
      return VerificationStage.rejectedMismatch;
    case 'QUALITY_TOO_LOW':
      return VerificationStage.qualityTooLow;
    case 'RETRY_REQUIRED':
      return VerificationStage.retryRequired;
  }
  // Fallbacks for older backends without ui_state.
  if (result.accepted) {
    return VerificationStage.verified;
  }
  if (result.rejectedMismatch) {
    return VerificationStage.rejectedMismatch;
  }
  if (result.rejectedSpoof) {
    return VerificationStage.rejectedSpoof;
  }
  if (result.retryRequired) {
    return result.qualityTooLow
        ? VerificationStage.qualityTooLow
        : VerificationStage.retryRequired;
  }
  return VerificationStage.processingError;
}

class VerificationController extends Notifier<VerificationSession> {
  static const requiredFaceSamples = 3;
  static const requiredIrisSamples = 3;
  static const requiredVoiceSamples = 3;
  @override
  VerificationSession build() => VerificationSession.initial();

  VerificationRepository get _repository =>
      ref.read(verificationRepositoryProvider);

  void setConsent(bool value) {
    state = state.copyWith(consentGiven: value, errorMessage: null);
  }

  void addFaceSample(String path) {
    if (state.faceImagePaths.length >= requiredFaceSamples) return;
    final samples = [...state.faceImagePaths, path];
    _setStep(
      3,
      samples.length >= requiredFaceSamples
          ? VerificationStepStatus.passed
          : VerificationStepStatus.processing,
    );
    state = state.copyWith(
      faceImagePaths: samples,
      // Face frames are collected by the combined iris camera step. Never
      // expose a separate face stage in the UI.
      stage: state.irisImagePaths.length >= requiredIrisSamples
          ? VerificationStage.readyForVoice
          : VerificationStage.readyForIris,
      errorMessage: null,
    );
  }

  void clearFaceSamples() {
    final paths = state.faceImagePaths;
    state = state.copyWith(
      faceImagePaths: const [],
      stage: VerificationStage.readyForIris,
      errorMessage: null,
    );
    _setStep(3, VerificationStepStatus.pending);
    unawaited(_repository.deleteTemporaryMedia(paths));
  }

  Future<void> startBiometricCheck({required bool backendConnected}) async {
    if (!state.consentGiven) {
      state = state.copyWith(
        stage: VerificationStage.processingError,
        errorMessage:
            'Confirm biometric consent to begin the verification flow.',
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
    final previousPath = state.irisImagePath;
    if (previousPath != null && previousPath != path) {
      unawaited(_repository.deleteTemporaryMedia([previousPath]));
    }
    state = state.copyWith(
      irisImagePath: path,
      stage: VerificationStage.capturingIris,
      errorMessage: null,
    );
  }

  void clearOpenEyeImage() {
    final previousPath = state.irisImagePath;
    state = state.copyWith(
      irisImagePath: null,
      irisResult: null,
      errorMessage: null,
      stage: VerificationStage.readyForIris,
    );
    if (previousPath != null) {
      unawaited(_repository.deleteTemporaryMedia([previousPath]));
    }
  }

  void clearIrisSamples() {
    // Face and iris samples are captured from the same accepted frames, so a
    // retake must clear both modalities together.
    final paths = [
      ...state.faceImagePaths,
      ...state.irisImagePaths,
      state.irisImagePath,
    ];
    state = state.copyWith(
      faceImagePaths: const [],
      irisImagePaths: const [],
      irisImagePath: null,
      irisResult: null,
      errorMessage: null,
      stage: VerificationStage.readyForIris,
    );
    _setStep(4, VerificationStepStatus.pending);
    _setStep(3, VerificationStepStatus.pending);
    unawaited(_repository.deleteTemporaryMedia(paths));
  }

  void setVoiceFile(String path) {
    final previousPath = state.voiceFilePath;
    if (previousPath != null && previousPath != path) {
      unawaited(_repository.deleteTemporaryMedia([previousPath]));
    }
    state = state.copyWith(
      voiceFilePath: path,
      stage: VerificationStage.recordingVoice,
      errorMessage: null,
    );
    _setStep(5, VerificationStepStatus.processing);
    _setStep(6, VerificationStepStatus.processing);
  }

  void clearVoiceFile() {
    final previousPath = state.voiceFilePath;
    state = state.copyWith(
      voiceFilePath: null,
      voiceResult: null,
      errorMessage: null,
      stage: VerificationStage.readyForVoice,
    );
    if (previousPath != null) {
      unawaited(_repository.deleteTemporaryMedia([previousPath]));
    }
    final enrollmentInProgress = state.voiceFilePaths.isNotEmpty;
    final clearedStatus = enrollmentInProgress
        ? VerificationStepStatus.processing
        : VerificationStepStatus.pending;
    _setStep(5, clearedStatus);
    _setStep(6, clearedStatus);
  }

  void acceptVoiceSample(
    String path, {
    int requiredSamples = requiredVoiceSamples,
  }) {
    final required = requiredSamples < 1 ? 1 : requiredSamples;
    if (path.isEmpty || state.voiceFilePaths.length >= required) return;
    final samples = [...state.voiceFilePaths, path];
    final complete = samples.length >= required;
    _setStep(
      5,
      complete
          ? VerificationStepStatus.passed
          : VerificationStepStatus.processing,
    );
    _setStep(
      6,
      complete
          ? VerificationStepStatus.passed
          : VerificationStepStatus.processing,
    );
    state = state.copyWith(
      voiceFilePaths: samples,
      voiceFilePath: null,
      stage: complete
          ? VerificationStage.verification
          : VerificationStage.readyForVoice,
      errorMessage: null,
    );
  }

  void clearVoiceSamples() {
    final paths = [...state.voiceFilePaths, state.voiceFilePath];
    state = state.copyWith(
      voiceFilePaths: const [],
      voiceFilePath: null,
      voiceResult: null,
      errorMessage: null,
      stage: VerificationStage.readyForVoice,
    );
    _setStep(5, VerificationStepStatus.pending);
    _setStep(6, VerificationStepStatus.pending);
    unawaited(_repository.deleteTemporaryMedia(paths));
  }

  void clearEnrollmentSamples() {
    final paths = [
      ...state.faceImagePaths,
      ...state.irisImagePaths,
      state.irisImagePath,
      ...state.voiceFilePaths,
      state.voiceFilePath,
    ];
    state = state.copyWith(
      faceImagePaths: const [],
      irisImagePaths: const [],
      irisImagePath: null,
      voiceFilePaths: const [],
      voiceFilePath: null,
      irisResult: null,
      voiceResult: null,
      errorMessage: null,
      stage: VerificationStage.readyForIris,
    );
    for (final index in [3, 4, 5, 6, 7, 8]) {
      _setStep(index, VerificationStepStatus.pending);
    }
    unawaited(_repository.deleteTemporaryMedia(paths));
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
      status: micGranted
          ? VerificationStepStatus.passed
          : VerificationStepStatus.failed,
    );
    state = state.copyWith(
      steps: steps,
      stage: cameraGranted && micGranted
          ? VerificationStage.readyForIris
          : VerificationStage.processingError,
      errorMessage: cameraGranted && micGranted
          ? null
          : 'Camera and microphone access are required for biometric verification.',
    );
  }

  Future<bool> verifyIrisStep({String eyeSide = 'LEFT'}) async {
    if (state.irisImagePath == null || state.irisImagePath!.isEmpty) {
      state = state.copyWith(
        stage: VerificationStage.irisFailed,
        errorMessage: 'Capture an open-eye image first.',
      );
      return false;
    }
    _setStep(4, VerificationStepStatus.processing);
    state = state.copyWith(stage: VerificationStage.processingIris);
    try {
      final result = await _repository.verifyIrisStep(
        imagePath: state.irisImagePath!,
        eyeSide: eyeSide,
      );
      final acceptedPaths = result.passed
          ? [...state.irisImagePaths, state.irisImagePath!]
          : state.irisImagePaths;
      _setStep(
        4,
        acceptedPaths.length >= requiredIrisSamples
            ? VerificationStepStatus.passed
            : result.passed
            ? VerificationStepStatus.processing
            : VerificationStepStatus.failed,
      );
      state = state.copyWith(
        irisImagePaths: acceptedPaths,
        irisImagePath: result.passed ? null : state.irisImagePath,
        irisResult: result,
        stage: result.passed
            ? acceptedPaths.length >= requiredIrisSamples
                  ? VerificationStage.readyForVoice
                  : VerificationStage.readyForIris
            : VerificationStage.irisFailed,
        errorMessage: result.passed
            ? acceptedPaths.length < requiredIrisSamples
                  ? 'Captured ${acceptedPaths.length} of $requiredIrisSamples stable iris samples.'
                  : null
            : result.message,
      );
      return acceptedPaths.length >= requiredIrisSamples;
    } catch (error) {
      _setStep(4, VerificationStepStatus.failed);
      state = state.copyWith(
        stage: VerificationStage.irisFailed,
        errorMessage: error.toString(),
      );
      return false;
    }
  }

  /// Accept the camera frame immediately for the prototype face-primary
  /// workflow. The frame is stored in both upload collections so the backend
  /// can generate the face template while the UI continues to call this step
  /// an iris capture. Iris segmentation, when enabled by the backend, is
  /// still performed later during enrollment/verification.
  void acceptIrisCapture(
    String path, {
    int requiredSamples = requiredIrisSamples,
  }) {
    final required = requiredSamples < 1 ? 1 : requiredSamples;
    if (path.isEmpty || state.irisImagePaths.length >= required) {
      return;
    }
    final irisSamples = [...state.irisImagePaths, path];
    final faceSamples = [...state.faceImagePaths, path];
    _setStep(
      4,
      irisSamples.length >= required
          ? VerificationStepStatus.passed
          : VerificationStepStatus.processing,
    );
    _setStep(
      3,
      faceSamples.length >= required
          ? VerificationStepStatus.passed
          : VerificationStepStatus.processing,
    );
    state = state.copyWith(
      irisImagePaths: irisSamples,
      faceImagePaths: faceSamples,
      irisImagePath: null,
      irisResult: null,
      stage: irisSamples.length >= required
          ? VerificationStage.readyForVoice
          : VerificationStage.readyForIris,
      errorMessage: null,
    );
  }

  Future<bool> verifyVoiceStep() async {
    if (state.voiceFilePath == null || state.voiceFilePath!.isEmpty) {
      state = state.copyWith(
        stage: VerificationStage.voiceFailed,
        errorMessage: 'Capture a spoken response first.',
      );
      return false;
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
        stage: result.passed
            ? VerificationStage.fusingScores
            : VerificationStage.voiceFailed,
        errorMessage: result.passed ? null : result.message,
      );
      return result.passed;
    } catch (error) {
      _setStep(6, VerificationStepStatus.failed);
      state = state.copyWith(
        stage: VerificationStage.voiceFailed,
        errorMessage: error.toString(),
      );
      return false;
    }
  }

  Future<String?> enroll({
    required String userId,
    String eyeSide = 'LEFT',
  }) async {
    if (state.faceImagePaths.length < requiredFaceSamples ||
        state.irisImagePaths.length < requiredIrisSamples ||
        state.voiceFilePaths.length < requiredVoiceSamples) {
      state = state.copyWith(
        stage: VerificationStage.processingError,
        errorMessage:
            'Capture $requiredIrisSamples camera photos and $requiredVoiceSamples voice samples before enrollment.',
      );
      return null;
    }
    state = state.copyWith(stage: VerificationStage.verification);
    _setStep(7, VerificationStepStatus.processing);
    _setStep(8, VerificationStepStatus.processing);
    try {
      final message = await _repository.enrollBiometrics(
        userId: userId,
        facePaths: state.faceImagePaths,
        irisPaths: state.irisImagePaths,
        voicePaths: state.voiceFilePaths,
        eyeSide: eyeSide,
      );
      _setStep(7, VerificationStepStatus.passed);
      _setStep(8, VerificationStepStatus.passed);
      state = state.copyWith(
        stage: VerificationStage.verified,
        errorMessage: null,
      );
      return message;
    } catch (error) {
      _setStep(7, VerificationStepStatus.failed);
      _setStep(8, VerificationStepStatus.failed);
      state = state.copyWith(
        stage: VerificationStage.retryRequired,
        errorMessage: error.toString(),
      );
      return null;
    }
  }

  Future<VerificationResult?> finalize({
    required String userId,
    String eyeSide = 'LEFT',
    int minimumSamples = 1,
  }) async {
    final required = minimumSamples < 1 ? 1 : minimumSamples;
    if (state.faceImagePaths.length < required ||
        state.irisImagePaths.length < required ||
        state.voiceFilePath == null) {
      state = state.copyWith(
        stage: VerificationStage.processingError,
        errorMessage:
            'A camera sample and voice recording are required before final verification.',
      );
      return null;
    }

    _setStep(7, VerificationStepStatus.processing);
    _setStep(8, VerificationStepStatus.processing);
    state = state.copyWith(stage: VerificationStage.fusingScores);

    try {
      final result = await _repository.completeVerification(
        userId: userId,
        facePaths: state.faceImagePaths,
        irisPaths: state.irisImagePaths,
        voicePath: state.voiceFilePath!,
        eyeSide: eyeSide,
        challengePhrase: AppConstants.verificationPhrase,
      );
      _setStep(
        7,
        result.fusion.score >= result.fusion.threshold
            ? VerificationStepStatus.passed
            : VerificationStepStatus.failed,
      );
      final stage = stageForResult(result);
      _setStep(8, switch (stage) {
        VerificationStage.verified => VerificationStepStatus.passed,
        VerificationStage.qualityTooLow ||
        VerificationStage.retryRequired => VerificationStepStatus.pending,
        _ => VerificationStepStatus.failed,
      });
      state = state.copyWith(
        finalResult: result,
        stage: stage,
        errorMessage:
            result.failureReason ??
            (result.accepted ? null : result.reasonMessage),
      );
      return result;
    } catch (error) {
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
      ...state.faceImagePaths,
      ...state.irisImagePaths,
      state.irisImagePath,
      ...state.voiceFilePaths,
      state.voiceFilePath,
    ]);
  }

  void restart() {
    final paths = [
      ...state.faceImagePaths,
      ...state.irisImagePaths,
      state.irisImagePath,
      ...state.voiceFilePaths,
      state.voiceFilePath,
    ];
    state = VerificationSession.initial();
    unawaited(_repository.deleteTemporaryMedia(paths));
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
