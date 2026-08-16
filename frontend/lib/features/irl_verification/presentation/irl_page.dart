import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/constants/app_constants.dart';
import '../../../core/routing/route_names.dart';
import '../../../core/widgets/error_panel.dart';
import '../../../shared/models/result_navigation_payload.dart';
import '../../../shared/widgets/page_header.dart';
import '../../backend_health/providers/backend_health_provider.dart';
import '../models/verification_step.dart';
import '../providers/verification_controller.dart';
import 'widgets/iris_verification_step.dart';
import 'widgets/verification_card.dart';
import 'widgets/verification_stepper.dart';
import 'widgets/voice_verification_step.dart';

class IrlPage extends ConsumerStatefulWidget {
  const IrlPage({super.key});

  @override
  ConsumerState<IrlPage> createState() => _IrlPageState();
}

class _IrlPageState extends ConsumerState<IrlPage> {
  String _eyeSide = 'LEFT';

  @override
  void dispose() {
    Future<void>.microtask(
      () => ref.read(verificationProvider.notifier).cleanup(),
    );
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(verificationProvider);
    ref.watch(backendHealthProvider);

    return ListView(
      children: [
        const PageHeader(
          title: 'IRL Human Verification',
          subtitle:
              'Tick the checkbox, complete the blink challenge, speak the phrase, and get a verified-as-human result.',
        ),
        const SizedBox(height: 16),
        VerificationCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'AI Human Verification',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              const Text(
                'This flow performs a privacy-first camera and voice challenge without saving the completed verification.',
              ),
              const SizedBox(height: 16),
              const Card(
                child: Padding(
                  padding: EdgeInsets.all(16),
                  child: Text(AppConstants.irlConsentNotice),
                ),
              ),
              const SizedBox(height: 16),
              CheckboxListTile(
                value: session.consentGiven,
                title: const Text('I am not a robot'),
                subtitle: const Text(
                  'Checking this begins the blink and speak challenge automatically after permissions are granted.',
                ),
                onChanged: (value) async {
                  final checked = value ?? false;
                  ref.read(verificationProvider.notifier).setConsent(checked);
                  if (!checked) {
                    ref.read(verificationProvider.notifier).restart();
                    return;
                  }
                  final backend = await ref
                      .read(backendHealthProvider.notifier)
                      .refreshStatus();
                  await ref
                      .read(verificationProvider.notifier)
                      .startHumanCheck(backendConnected: backend.connected);
                },
              ),
              const SizedBox(height: 20),
              VerificationProgressStepper(steps: session.steps),
              if (session.errorMessage != null) ...[
                const SizedBox(height: 16),
                ErrorPanel(message: session.errorMessage!),
              ],
              const SizedBox(height: 20),
              if (session.stage == VerificationStage.readyForIris ||
                  session.stage == VerificationStage.capturingIris ||
                  session.stage == VerificationStage.irisFailed) ...[
                Text(
                  'Step 1: Look into the guide with one eye open',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 8),
                LiveCameraPanel(
                  instructions: const [
                    'Move the camera close to one eye',
                    'Keep your eye open and centered',
                    'Keep the image steady',
                    'Use clear lighting',
                  ],
                  capturedPath: session.irisImagePath,
                  captureButtonLabel: 'Capture Open Eye',
                  onCaptured: (path) async {
                    ref
                        .read(verificationProvider.notifier)
                        .setOpenEyeImage(path);
                    await ref
                        .read(verificationProvider.notifier)
                        .verifyIrisStep(eyeSide: _eyeSide);
                  },
                  onRetake: () => ref
                      .read(verificationProvider.notifier)
                      .clearOpenEyeImage(),
                ),
                const SizedBox(height: 12),
                SegmentedButton<String>(
                  segments: const [
                    ButtonSegment(value: 'LEFT', label: Text('Left eye')),
                    ButtonSegment(value: 'RIGHT', label: Text('Right eye')),
                  ],
                  selected: {_eyeSide},
                  onSelectionChanged: (value) =>
                      setState(() => _eyeSide = value.first),
                ),
              ],
              if (session.stage == VerificationStage.readyForBlink ||
                  session.stage == VerificationStage.capturingBlink ||
                  session.stage == VerificationStage.blinkFailed) ...[
                const SizedBox(height: 20),
                Text(
                  'Step 2: Blink once when ready, then capture the blink frame',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 8),
                LiveCameraPanel(
                  instructions: const [
                    'Keep your face aligned with the camera',
                    'Blink once naturally',
                    'Capture the frame right after the blink',
                    'Retake if the eye is not clear',
                  ],
                  capturedPath: session.blinkImagePath,
                  captureButtonLabel: 'Capture Blink',
                  onCaptured: (path) {
                    ref.read(verificationProvider.notifier).setBlinkImage(path);
                    ref
                        .read(verificationProvider.notifier)
                        .advanceToVoiceAfterBlink();
                  },
                  onRetake: () =>
                      ref.read(verificationProvider.notifier).clearBlinkImage(),
                ),
              ],
              if (session.stage == VerificationStage.readyForVoice ||
                  session.stage == VerificationStage.voiceFailed ||
                  session.stage == VerificationStage.recordingVoice) ...[
                const SizedBox(height: 20),
                VoiceRecorderPanel(
                  recordedPath: session.voiceFilePath,
                  autoStartRecording: true,
                  title: 'Step 3: Speak the challenge phrase',
                  phrase: AppConstants.verificationPhrase,
                  onRecorded: (path, _) async {
                    ref.read(verificationProvider.notifier).setVoiceFile(path);
                    await ref
                        .read(verificationProvider.notifier)
                        .verifyVoiceStep();
                    final result = await ref
                        .read(verificationProvider.notifier)
                        .finalize(eyeSide: _eyeSide);
                    if (!context.mounted || result == null) {
                      return;
                    }
                    context.goNamed(
                      RouteNames.irlResult,
                      extra: ResultNavigationPayload(result: result),
                    );
                  },
                  onRetake: () =>
                      ref.read(verificationProvider.notifier).clearVoiceFile(),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}
