import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/constants/verification_constants.dart';
import '../../../core/io/local_file_cleanup.dart';
import '../../../core/networking/dio_client.dart';
import '../data/test_repository.dart';
import '../models/voice_test_result.dart';
import 'iris_test_controller.dart';

const _sentinel = Object();

class VoiceTestState {
  const VoiceTestState({
    required this.mode,
    required this.isProcessing,
    required this.processingStages,
    this.audioPath,
    this.durationSeconds,
    this.result,
    this.errorMessage,
    this.uploadProgress = 0,
  });

  final TestComparisonMode mode;
  final bool isProcessing;
  final List<String> processingStages;
  final String? audioPath;
  final double? durationSeconds;
  final VoiceTestResult? result;
  final String? errorMessage;
  final double uploadProgress;

  factory VoiceTestState.initial() => const VoiceTestState(
    mode: TestComparisonMode.qualityOnly,
    isProcessing: false,
    processingStages: [],
  );

  VoiceTestState copyWith({
    TestComparisonMode? mode,
    bool? isProcessing,
    List<String>? processingStages,
    Object? audioPath = _sentinel,
    Object? durationSeconds = _sentinel,
    Object? result = _sentinel,
    Object? errorMessage = _sentinel,
    double? uploadProgress,
  }) {
    return VoiceTestState(
      mode: mode ?? this.mode,
      isProcessing: isProcessing ?? this.isProcessing,
      processingStages: processingStages ?? this.processingStages,
      audioPath: identical(audioPath, _sentinel)
          ? this.audioPath
          : audioPath as String?,
      durationSeconds: identical(durationSeconds, _sentinel)
          ? this.durationSeconds
          : durationSeconds as double?,
      result: identical(result, _sentinel)
          ? this.result
          : result as VoiceTestResult?,
      errorMessage: identical(errorMessage, _sentinel)
          ? this.errorMessage
          : errorMessage as String?,
      uploadProgress: uploadProgress ?? this.uploadProgress,
    );
  }
}

class VoiceTestController extends Notifier<VoiceTestState> {
  @override
  VoiceTestState build() => VoiceTestState.initial();

  TestRepository get _repository => TestRepository(ref.read(dioProvider));

  void setAudio({required String path, required double durationSeconds}) {
    state = state.copyWith(
      audioPath: path,
      durationSeconds: durationSeconds,
      result: null,
      errorMessage: null,
    );
  }

  Future<void> clearAudio() async {
    await deleteLocalFileIfExists(state.audioPath);
    state = state.copyWith(
      audioPath: null,
      durationSeconds: null,
      result: null,
      errorMessage: null,
      uploadProgress: 0,
    );
  }

  Future<void> analyze() async {
    final audioPath = state.audioPath;
    if (audioPath == null) {
      state = state.copyWith(
        errorMessage: 'Record a voice sample before analysis.',
      );
      return;
    }

    state = state.copyWith(
      isProcessing: true,
      processingStages: VerificationConstants.voiceProcessingStages,
      uploadProgress: 0,
      errorMessage: null,
    );
    try {
      final result = await _repository.analyzeVoice(
        audioPath: audioPath,
        onSendProgress: (sent, total) {
          state = state.copyWith(uploadProgress: total == 0 ? 0 : sent / total);
        },
      );
      state = state.copyWith(
        isProcessing: false,
        result: result,
        processingStages: const [],
      );
    } catch (error) {
      state = state.copyWith(
        isProcessing: false,
        errorMessage: error.toString(),
        processingStages: const [],
      );
    }
  }
}

final voiceTestProvider = NotifierProvider<VoiceTestController, VoiceTestState>(
  VoiceTestController.new,
);
