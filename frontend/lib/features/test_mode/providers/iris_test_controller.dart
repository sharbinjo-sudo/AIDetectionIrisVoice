import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/constants/verification_constants.dart';
import '../../../core/networking/dio_client.dart';
import '../data/test_repository.dart';
import '../models/iris_test_result.dart';

enum TestComparisonMode { qualityOnly }

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
    String? capturedImagePath,
    String? eyeSide,
    IrisTestResult? result,
    String? errorMessage,
    double? uploadProgress,
  }) {
    return IrisTestState(
      mode: mode ?? this.mode,
      isProcessing: isProcessing ?? this.isProcessing,
      processingStages: processingStages ?? this.processingStages,
      capturedImagePath: capturedImagePath ?? this.capturedImagePath,
      eyeSide: eyeSide ?? this.eyeSide,
      result: result ?? this.result,
      errorMessage: errorMessage,
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
    state = state.copyWith(capturedImagePath: path, result: null, errorMessage: null);
  }

  Future<void> clearCapture() async {
    if (!kIsWeb && state.capturedImagePath != null) {
      final file = File(state.capturedImagePath!);
      if (await file.exists()) {
        await file.delete();
      }
    }
    state = state.copyWith(capturedImagePath: null, result: null, errorMessage: null);
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
          state = state.copyWith(
            uploadProgress: total == 0 ? 0 : sent / total,
          );
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

final irisTestProvider =
    NotifierProvider<IrisTestController, IrisTestState>(IrisTestController.new);
