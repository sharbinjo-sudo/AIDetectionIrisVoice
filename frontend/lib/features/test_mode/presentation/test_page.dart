import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/constants/app_constants.dart';
import '../../../core/widgets/error_panel.dart';
import '../../../core/widgets/loading_overlay.dart';
import '../../../shared/widgets/page_header.dart';
import '../providers/iris_test_controller.dart';
import '../providers/voice_test_controller.dart';
import 'widgets/iris_test_result_panel.dart';
import 'widgets/live_camera_panel.dart';
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

  @override
  void dispose() {
    Future<void>.microtask(() async {
      await ref.read(irisTestProvider.notifier).clearCapture();
      await ref.read(voiceTestProvider.notifier).clearAudio();
    });
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final stacked = width < AppConstants.mobileBreakpoint;
    final irisState = ref.watch(irisTestProvider);
    final voiceState = ref.watch(voiceTestProvider);

    return Stack(
      children: [
        ListView(
          children: [
            const PageHeader(
              title: 'Test Mode',
              subtitle:
                  'Temporarily test the eye camera and voice challenge quality without saving a permanent result or comparing against registered users.',
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
              LiveCameraPanel(
                instructions: const [
                  'Move the camera close to one eye',
                  'Keep the eye open and inside the guide',
                  'Keep the image steady',
                  'Avoid reflections',
                  'Use clear lighting',
                ],
                capturedPath: irisState.capturedImagePath,
                captureButtonLabel: 'Capture Eye Image',
                onCaptured: (path) =>
                    ref.read(irisTestProvider.notifier).setCapturedImage(path),
                onRetake: () => ref.read(irisTestProvider.notifier).clearCapture(),
              ),
              const SizedBox(height: 12),
              FilledButton(
                onPressed: irisState.capturedImagePath == null || irisState.isProcessing
                    ? null
                    : () => ref.read(irisTestProvider.notifier).analyze(),
                child: const Text('Analyse Eye Quality'),
              ),
              if (irisState.errorMessage != null) ...[
                const SizedBox(height: 12),
                ErrorPanel(message: irisState.errorMessage!),
              ],
              if (irisState.result != null) ...[
                const SizedBox(height: 16),
                IrisTestResultPanel(result: irisState.result!),
              ],
            ] else ...[
              VoiceRecorderPanel(
                recordedPath: voiceState.audioPath,
                title: 'Voice Challenge Test',
                phrase: AppConstants.verificationPhrase,
                onRecorded: (path, durationSeconds) {
                  ref.read(voiceTestProvider.notifier).setAudio(
                        path: path,
                        durationSeconds: durationSeconds,
                      );
                },
                onRetake: () => ref.read(voiceTestProvider.notifier).clearAudio(),
              ),
              const SizedBox(height: 12),
              FilledButton(
                onPressed: voiceState.audioPath == null || voiceState.isProcessing
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
          visible: irisState.isProcessing || voiceState.isProcessing,
          message: 'Processing temporary quality test...',
        ),
      ],
    );
  }
}
