import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/constants/verification_constants.dart';
import '../../../core/io/local_file_cleanup.dart';
import '../../../core/networking/dio_client.dart';
import '../data/test_repository.dart';
import '../models/iris_test_result.dart';

enum TestComparisonMode { qualityOnly }

const _sentinel = Object();

class IrisTestState {
  const IrisTestState({
    required this.mode,
    required this.isProcessing,
    required this.processingStages,
    this.capturedImagePath,
    this.eyeSide = 'LEFT',
    this.result,
    this.errorMessage,
    this.uploadProgress = 0,
  });

  final TestComparisonMode mode;
  final bool isProcessing;
  final List<String> processingStages;
  final String? capturedImagePath;
  final String eyeSide;
  final IrisTestResult? result;
  final String? errorMessage;
  final double uploadProgress;

  factory IrisTestState.initial() => const IrisTestState(
    mode: TestComparisonMode.qualityOnly,
    isProcessing: false,
    processingStages: [],
  );

  IrisTestState copyWith({
    TestComparisonMode? mode,
    bool? isProcessing,
    List<String>? processingStages,
    Object? capturedImagePath = _sentinel,
    String? eyeSide,
    Object? result = _sentinel,
    Object? errorMessage = _sentinel,
    double? uploadProgress,
  }) {
    return IrisTestState(
      mode: mode ?? this.mode,
      isProcessing: isProcessing ?? this.isProcessing,
      processingStages: processingStages ?? this.processingStages,
      capturedImagePath: identical(capturedImagePath, _sentinel)
          ? this.capturedImagePath
          : capturedImagePath as String?,
      eyeSide: eyeSide ?? this.eyeSide,
      result: identical(result, _sentinel)
          ? this.result
          : result as IrisTestResult?,
      errorMessage: identical(errorMessage, _sentinel)
          ? this.errorMessage
          : errorMessage as String?,
      uploadProgress: uploadProgress ?? this.uploadProgress,
    );
  }
}

class IrisTestController extends Notifier<IrisTestState> {
  @override
  IrisTestState build() => IrisTestState.initial();

  TestRepository get _repository => TestRepository(ref.read(dioProvider));

  void setEyeSide(String eyeSide) {
    state = state.copyWith(eyeSide: eyeSide);
  }

  void setCapturedImage(String path) {
    state = state.copyWith(
      capturedImagePath: path,
      result: null,
      errorMessage: null,
    );
  }

  Future<void> clearCapture() async {
    await deleteLocalFileIfExists(state.capturedImagePath);
    state = state.copyWith(
      capturedImagePath: null,
      result: null,
      errorMessage: null,
    );
  }

  Future<void> analyze() async {
    final imagePath = state.capturedImagePath;
    if (imagePath == null) {
      state = state.copyWith(
        errorMessage: 'Capture an eye image before analysis.',
      );
      return;
    }

    state = state.copyWith(
      isProcessing: true,
      processingStages: VerificationConstants.irisProcessingStages,
      uploadProgress: 0,
      errorMessage: null,
    );
    try {
      final result = await _repository.analyzeIris(
        imagePath: imagePath,
        eyeSide: state.eyeSide,
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

final irisTestProvider = NotifierProvider<IrisTestController, IrisTestState>(
  IrisTestController.new,
);
