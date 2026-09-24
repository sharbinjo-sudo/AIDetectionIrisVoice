import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/constants/app_constants.dart';
import '../../../core/io/local_file_cleanup.dart';
import '../../../core/widgets/error_panel.dart';
import '../../../core/widgets/loading_overlay.dart';
import '../../../shared/widgets/page_header.dart';
import '../../irl_verification/presentation/widgets/face_capture_panel.dart';
import '../providers/voice_test_controller.dart';
import '../providers/iris_test_controller.dart';
import 'widgets/iris_test_result_panel.dart';
import 'widgets/test_mode_selector.dart';
import 'widgets/voice_recorder_panel.dart';
import 'widgets/voice_test_result_panel.dart';

class TestPage extends ConsumerStatefulWidget {
  const TestPage({super.key});

  @override
  ConsumerState<TestPage> createState() => _TestPageState();
}

class _TestPageState extends ConsumerState<TestPage> {
  TestPanelType _selected = TestPanelType.iris;
  final List<String> _irisSamples = [];
  String? _voicePath;

  @override
  void dispose() {
    // Do not call controller methods that assign provider state from dispose.
    // Only remove the temporary files; the providers are discarded naturally.
    unawaited(deleteLocalFileIfExists(_voicePath));
    for (final path in _irisSamples) {
      unawaited(deleteLocalFileIfExists(path));
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    // The two test controls still need room for their labels and icons; use
    // the stacked layout before the narrow tablet breakpoint to avoid pixel
    // overflow in the segmented control.
    final stacked = width < 760;
    final voiceState = ref.watch(voiceTestProvider);
    _voicePath = voiceState.audioPath;
    final irisState = ref.watch(irisTestProvider);

    return Stack(
      children: [
        ListView(
          children: [
            const PageHeader(
              title: 'Test Mode',
              subtitle:
                  'Capture a camera or voice sample, then analyse its quality. Test Mode never grants access or creates an enrollment.',
            ),
            const SizedBox(height: 12),
            const Card(
              child: Padding(
                padding: EdgeInsets.all(18),
                child: Text(AppConstants.testConsentNotice),
              ),
            ),
            const SizedBox(height: 16),
            TestModeSelector(
              selected: _selected,
              stacked: stacked,
              onSelected: (panel) => setState(() => _selected = panel),
            ),
            const SizedBox(height: 20),
            if (_selected == TestPanelType.iris) ...[
              const Card(
                child: Padding(
                  padding: EdgeInsets.all(16),
                  child: Text(
                    'Capture a sample, then select Analyse Iris Quality to test it with the local backend. This is a capture-quality check, not identity verification.',
                  ),
                ),
              ),
              const SizedBox(height: 12),
              FaceCapturePanel(
                samplePaths: _irisSamples,
                requiredSamples: 1,
                onCaptured: (path) {
                  if (_irisSamples.isNotEmpty) return;
                  setState(() => _irisSamples.add(path));
                  ref.read(irisTestProvider.notifier).setCapturedImage(path);
                },
                onRetake: () {
                  setState(() => _irisSamples.clear());
                  unawaited(ref.read(irisTestProvider.notifier).clearCapture());
                },
              ),
              const SizedBox(height: 12),
              FilledButton(
                onPressed: _irisSamples.isEmpty || irisState.isProcessing
                    ? null
                    : () => ref.read(irisTestProvider.notifier).analyze(),
                child: const Text('Analyse Iris Quality'),
              ),
              if (_irisSamples.isEmpty)
                const Text('Capture a sample to enable analysis.'),
              if (_irisSamples.isNotEmpty && irisState.errorMessage != null)
                ErrorPanel(message: irisState.errorMessage!),
              if (_irisSamples.isNotEmpty && irisState.result != null)
                IrisTestResultPanel(result: irisState.result!),
            ] else ...[
              VoiceRecorderPanel(
                recordedPath: voiceState.audioPath,
                title: 'Voice Challenge Test',
                phrase: AppConstants.verificationPhrase,
                onRecorded: (path, durationSeconds) {
                  ref
                      .read(voiceTestProvider.notifier)
                      .setAudio(path: path, durationSeconds: durationSeconds);
                },
                onRetake: () =>
                    ref.read(voiceTestProvider.notifier).clearAudio(),
              ),
              const SizedBox(height: 12),
              FilledButton(
                onPressed:
                    voiceState.audioPath == null || voiceState.isProcessing
                    ? null
                    : () => ref.read(voiceTestProvider.notifier).analyze(),
                child: const Text('Analyse Voice Quality'),
              ),
              if (voiceState.errorMessage != null) ...[
                const SizedBox(height: 12),
                ErrorPanel(message: voiceState.errorMessage!),
              ],
              if (voiceState.result != null) ...[
                const SizedBox(height: 16),
                VoiceTestResultPanel(result: voiceState.result!),
              ],
            ],
          ],
        ),
        LoadingOverlay(
          visible: voiceState.isProcessing || irisState.isProcessing,
          message: 'Processing temporary quality test...',
        ),
      ],
    );
  }
}
