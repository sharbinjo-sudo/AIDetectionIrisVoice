import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/constants/app_constants.dart';
import '../../../core/routing/route_names.dart';
import '../../../core/widgets/error_panel.dart';
import '../../../shared/models/result_navigation_payload.dart';
import '../../../shared/widgets/page_header.dart';
import '../../backend_health/providers/backend_health_provider.dart';
import '../models/verification_session.dart';
import '../models/verification_step.dart';
import '../providers/verification_controller.dart';
import 'widgets/iris_verification_step.dart';
import 'widgets/enrollment_success_panel.dart';
import 'widgets/verification_card.dart';
import 'widgets/verification_stepper.dart';
import 'widgets/voice_verification_step.dart';

class IrlPage extends ConsumerStatefulWidget {
  const IrlPage({
    super.key,
    this.flow = 'standalone',
    this.userId,
    this.initialEyeSide,
  });

  final String flow;
  final String? userId;
  final String? initialEyeSide;

  @override
  ConsumerState<IrlPage> createState() => _IrlPageState();
}

class _IrlPageState extends ConsumerState<IrlPage> {
  late String _eyeSide;
  late VerificationController _controller;
  bool _enrollmentComplete = false;

  VerificationStepStatus _combinedStatus(
    VerificationSession session,
    List<int> indexes,
  ) {
    final statuses = indexes.map((index) => session.steps[index].status);
    if (statuses.contains(VerificationStepStatus.failed)) {
      return VerificationStepStatus.failed;
    }
    if (statuses.contains(VerificationStepStatus.processing)) {
      return VerificationStepStatus.processing;
    }
    if (statuses.every((status) => status == VerificationStepStatus.passed)) {
      return VerificationStepStatus.passed;
    }
    if (statuses.contains(VerificationStepStatus.unavailable)) {
      return VerificationStepStatus.unavailable;
    }
    return VerificationStepStatus.pending;
  }

  @override
  void initState() {
    super.initState();
    _controller = ref.read(verificationProvider.notifier);
    _eyeSide = widget.initialEyeSide?.toUpperCase() == 'RIGHT'
        ? 'RIGHT'
        : 'LEFT';
    // A provider cannot be mutated while Flutter is mounting this page.
    // Reset after the first frame so navigation into enrollment/verification
    // never triggers Riverpod's build-time mutation error.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      ref.read(verificationProvider.notifier).restart();
    });
  }

  @override
  void dispose() {
    unawaited(_controller.cleanup());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(verificationProvider);
    ref.watch(backendHealthProvider);

    if (_enrollmentComplete) {
      return EnrollmentSuccessPanel(
        onLogin: () => context.goNamed(RouteNames.login),
        onHome: () => context.goNamed(RouteNames.home),
      );
    }

    final enrolling = widget.flow == 'enrollment';
    final requiredCameraSamples = enrolling
        ? VerificationController.requiredIrisSamples
        : 1;
    final requiredVoiceSamples = enrolling
        ? VerificationController.requiredVoiceSamples
        : 1;
    final hasSessionUser = widget.userId?.isNotEmpty == true;
    final consentNotice = enrolling
        ? 'This enrollment sends three temporary camera photos and three voice recordings to the connected local Django server. Registration stores protected biometric templates; diagnostic scores and decisions may be retained locally for security auditing.'
        : AppConstants.irlConsentNotice;
    final displaySteps = enrolling
        ? [
            session.steps[0],
            session.steps[1],
            session.steps[2],
            VerificationStep(
              label:
                  'Camera samples (${session.irisImagePaths.length}/$requiredCameraSamples)',
              status: _combinedStatus(session, [3, 4]),
            ),
            VerificationStep(
              label:
                  'Voice samples (${session.voiceFilePaths.length}/$requiredVoiceSamples)',
              status: _combinedStatus(session, [5, 6]),
            ),
            VerificationStep(
              label: 'Save biometric templates',
              status: _combinedStatus(session, [7, 8]),
            ),
          ]
        : [
            VerificationStep(
              label: 'Camera verification',
              status: _combinedStatus(session, [3, 4]),
            ),
            VerificationStep(
              label: 'Voice verification',
              status: _combinedStatus(session, [5, 6]),
            ),
          ];

    return ListView(
      children: [
        PageHeader(
          title: enrolling ? 'Biometric Enrollment' : 'Biometric Verification',
          subtitle: enrolling
              ? 'Take three photos using Capture and record three voice samples. If you leave, log in with your existing customer ID and PIN to restart enrollment. Access stays locked until enrollment is complete.'
              : 'Use one camera sample and one voice sample to verify your existing templates.',
        ),
        const SizedBox(height: 16),
        if (!hasSessionUser) ...[
          VerificationCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Login or registration required',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 8),
                const Text(
                  'Start from the Home page. Registration opens biometric enrollment; login opens biometric verification.',
                ),
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: () => context.goNamed(RouteNames.home),
                  child: const Text('Go to Login / Registration'),
                ),
              ],
            ),
          ),
        ] else
          VerificationCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  enrolling ? 'Enroll Camera + Voice' : 'Verify Camera + Voice',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 8),
                Text(
                  enrolling
                      ? 'Registration builds templates from multiple quality-checked samples. Login uses a separate, single-capture verification flow.'
                      : 'Login checks one fresh camera sample and one voice recording against the templates saved during registration.',
                ),
                const SizedBox(height: 16),
                Card(
                  child: Padding(
                    padding: EdgeInsets.all(16),
                    child: Text(consentNotice),
                  ),
                ),
                const SizedBox(height: 16),
                CheckboxListTile(
                  value: session.consentGiven,
                  title: Text(
                    enrolling
                        ? 'I consent to biometric enrollment'
                        : 'Begin biometric verification',
                  ),
                  subtitle: Text(
                    enrolling
                        ? 'This records three camera samples and three voice samples for protected enrollment templates.'
                        : 'This compares live captures with your registered templates.',
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
                        .startBiometricCheck(
                          backendConnected: backend.connected,
                        );
                  },
                ),
                const SizedBox(height: 20),
                VerificationProgressStepper(steps: displaySteps),
                if (session.errorMessage != null) ...[
                  const SizedBox(height: 16),
                  ErrorPanel(message: session.errorMessage!),
                ],
                if (session.stage == VerificationStage.qualityTooLow ||
                    session.stage == VerificationStage.retryRequired) ...[
                  const SizedBox(height: 16),
                  Card(
                    color: Colors.orange.withValues(alpha: 0.08),
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              const Icon(
                                Icons.autorenew_rounded,
                                color: Colors.orange,
                              ),
                              const SizedBox(width: 8),
                              Text(
                                session.stage == VerificationStage.qualityTooLow
                                    ? 'Capture quality too low'
                                    : 'Retake required',
                                style: Theme.of(context).textTheme.titleMedium,
                              ),
                            ],
                          ),
                          const SizedBox(height: 8),
                          Text(
                            session.errorMessage ??
                                'Poor capture quality is not treated as a verification failure. '
                                    'Retake the affected capture and try again.',
                          ),
                          const SizedBox(height: 12),
                          Wrap(
                            spacing: 12,
                            runSpacing: 10,
                            children: enrolling
                                ? [
                                    FilledButton.icon(
                                      icon: const Icon(Icons.refresh_rounded),
                                      label: const Text(
                                        'Retake all enrollment samples',
                                      ),
                                      onPressed: () => ref
                                          .read(verificationProvider.notifier)
                                          .clearEnrollmentSamples(),
                                    ),
                                  ]
                                : [
                                    FilledButton.icon(
                                      icon: const Icon(
                                        Icons.camera_alt_rounded,
                                      ),
                                      label: const Text('Retake camera sample'),
                                      onPressed: () => ref
                                          .read(verificationProvider.notifier)
                                          .clearIrisSamples(),
                                    ),
                                    OutlinedButton.icon(
                                      icon: const Icon(Icons.mic_rounded),
                                      label: const Text('Retake voice'),
                                      onPressed: () => ref
                                          .read(verificationProvider.notifier)
                                          .clearVoiceFile(),
                                    ),
                                  ],
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
                const SizedBox(height: 20),
                if (session.stage == VerificationStage.readyForIris ||
                    session.stage == VerificationStage.capturingIris ||
                    session.stage == VerificationStage.irisFailed ||
                    session.stage == VerificationStage.qualityTooLow ||
                    session.stage == VerificationStage.retryRequired) ...[
                  Text(
                    'Step 1: Capture ${enrolling ? 'camera samples' : 'camera sample'} '
                    '(${session.irisImagePaths.length}/$requiredCameraSamples)',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    enrolling
                        ? 'Keep your full head in the camera frame, then press Capture for each photo. Capture count does not mean quality checks have passed; samples are validated before enrollment is saved.'
                        : 'Keep your full head visible and steady, then press Capture. Identity matching runs after you submit your samples.',
                  ),
                  const SizedBox(height: 8),
                  LiveCameraPanel(
                    instructions: [
                      'Keep your full head centered; do not zoom in on one eye',
                      'Only one person should be visible',
                      'Look toward the camera and keep the image steady',
                      'Use even front lighting; avoid strong backlighting',
                    ],
                    requiredStableFrames: enrolling ? 3 : 2,
                    requiredEyeSide: _eyeSide,
                    onStableFrameProgress: (current, required) {},
                    capturedPath: session.irisImagePath,
                    captureButtonLabel: 'Capture Photo',
                    onCaptured: (path) {
                      // The camera step is labelled as iris for the user, but
                      // each full frame is immediately retained for the face
                      // template as well. Backend policy decides whether iris
                      // segmentation is required; capture itself never waits
                      // on a low-quality iris mask.
                      ref
                          .read(verificationProvider.notifier)
                          .acceptIrisCapture(
                            path,
                            requiredSamples: requiredCameraSamples,
                          );
                    },
                    onRetake: () => ref
                        .read(verificationProvider.notifier)
                        .clearIrisSamples(),
                  ),
                  const SizedBox(height: 12),
                  SegmentedButton<String>(
                    segments: const [
                      ButtonSegment(value: 'LEFT', label: Text('Left eye')),
                      ButtonSegment(value: 'RIGHT', label: Text('Right eye')),
                    ],
                    selected: {_eyeSide},
                    onSelectionChanged: enrolling
                        ? (value) => setState(() => _eyeSide = value.first)
                        : null,
                  ),
                ],
                if (session.stage == VerificationStage.readyForVoice ||
                    session.stage == VerificationStage.voiceFailed ||
                    session.stage == VerificationStage.recordingVoice) ...[
                  const SizedBox(height: 20),
                  Text(
                    enrolling
                        ? 'Step 2: Capture voice samples (${session.voiceFilePaths.length}/$requiredVoiceSamples)'
                        : 'Step 2: Voice verification',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 8),
                  if (enrolling && session.voiceFilePaths.isNotEmpty) ...[
                    LinearProgressIndicator(
                      value:
                          session.voiceFilePaths.length / requiredVoiceSamples,
                    ),
                    const SizedBox(height: 8),
                    Align(
                      alignment: Alignment.centerRight,
                      child: TextButton.icon(
                        onPressed: () => ref
                            .read(verificationProvider.notifier)
                            .clearVoiceSamples(),
                        icon: const Icon(Icons.refresh_rounded),
                        label: const Text('Retake voice samples'),
                      ),
                    ),
                  ],
                  VoiceRecorderPanel(
                    key: ValueKey(
                      enrolling
                          ? 'enrollment-voice-${session.voiceFilePaths.length}'
                          : 'login-voice',
                    ),
                    recordedPath: session.voiceFilePath,
                    autoStartRecording: true,
                    title: enrolling
                        ? 'Voice enrollment sample ${session.voiceFilePaths.length + 1} of $requiredVoiceSamples'
                        : 'Speak to verify your voice',
                    phrase: AppConstants.verificationPhrase,
                    onRecorded: (path, _) async {
                      ref
                          .read(verificationProvider.notifier)
                          .setVoiceFile(path);
                      final voicePassed = await ref
                          .read(verificationProvider.notifier)
                          .verifyVoiceStep();
                      if (!voicePassed || !context.mounted) {
                        return;
                      }
                      if (enrolling) {
                        final controller = ref.read(
                          verificationProvider.notifier,
                        );
                        controller.acceptVoiceSample(
                          path,
                          requiredSamples: requiredVoiceSamples,
                        );
                        if (ref
                                .read(verificationProvider)
                                .voiceFilePaths
                                .length <
                            requiredVoiceSamples) {
                          return;
                        }
                        final message = await ref
                            .read(verificationProvider.notifier)
                            .enroll(userId: widget.userId!, eyeSide: _eyeSide);
                        if (!context.mounted || message == null) {
                          return;
                        }
                        await ref.read(verificationProvider.notifier).cleanup();
                        if (!context.mounted) return;
                        ref.read(verificationProvider.notifier).restart();
                        setState(() => _enrollmentComplete = true);
                        return;
                      }
                      final result = await ref
                          .read(verificationProvider.notifier)
                          .finalize(
                            userId: widget.userId!,
                            eyeSide: _eyeSide,
                            minimumSamples: requiredCameraSamples,
                          );
                      if (!context.mounted || result == null) return;
                      context.goNamed(
                        RouteNames.irlResult,
                        queryParameters: {
                          'flow': 'verification',
                          'user': widget.userId!,
                        },
                        extra: ResultNavigationPayload(
                          result: result,
                          userId: widget.userId!,
                          eyeSide: _eyeSide,
                        ),
                      );
                    },
                    onRetake: () => ref
                        .read(verificationProvider.notifier)
                        .clearVoiceFile(),
                  ),
                ],
              ],
            ),
          ),
      ],
    );
  }
}
