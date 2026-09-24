import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_names.dart';
import '../../../core/widgets/secondary_button.dart';
import '../../../shared/models/result_navigation_payload.dart';
import '../../../shared/widgets/biometric_score_card.dart';
import '../models/verification_result.dart';
import '../providers/verification_controller.dart';
import 'widgets/verification_failed_panel.dart';
import 'widgets/verified_success_panel.dart';

class VerificationResultPage extends ConsumerWidget {
  const VerificationResultPage({super.key, required this.payload});

  final ResultNavigationPayload payload;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final result = payload.result;
    final verified = result.accepted;
    final width = MediaQuery.sizeOf(context).width;
    final irisCaptureOnly =
        result.fusion.irisWeight == 0 &&
        result.reasonCode == 'FACE_VOICE_VALID_IRIS_CAPTURE_ONLY';

    // "Biometric Verification Failed" is reserved for actual mismatch or
    // spoof evidence. Quality/retry outcomes show guidance instead.
    final Widget panel;
    if (verified) {
      panel = VerifiedSuccessPanel(irisCaptureOnly: irisCaptureOnly);
    } else if (result.rejectedMismatch || result.rejectedSpoof) {
      panel = VerificationFailedPanel(
        message:
            result.failureReason ??
            result.reasonMessage ??
            'The verification checks did not pass.',
        rejectionType: result.rejectedSpoof
            ? RejectionType.spoof
            : RejectionType.mismatch,
      );
    } else if (result.processingError) {
      panel = VerificationFailedPanel(
        message:
            result.failureReason ??
            'Verification could not complete. Please try again.',
        retryRequired: true,
      );
    } else {
      // RETRY_REQUIRED / QUALITY_TOO_LOW: poor capture, not identity evidence.
      panel = VerificationFailedPanel(
        retryRequired: true,
        message:
            result.failureReason ??
            result.reasonMessage ??
            'Capture quality is insufficient. Retake the affected capture.',
        qualityDetail: _qualityDetail(result, irisCaptureOnly),
      );
    }

    return ListView(
      key: const PageStorageKey<String>('verification-result'),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              children: [
                panel,
                const SizedBox(height: 20),
                Text('Processing time: ${result.processingTimeMs} ms'),
                const SizedBox(height: 8),
                const Text(
                  'Biometric media is deleted after processing. Diagnostic scores and the decision may be recorded locally for auditing.',
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        GridView.count(
          crossAxisCount: width > 1100
              ? 3
              : width > 700
              ? 2
              : 1,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          crossAxisSpacing: 16,
          mainAxisSpacing: 16,
          mainAxisExtent: width > 700 ? 290 : 270,
          children: [
            BiometricScoreCard(
              label: 'Iris verification',
              value: result.face.normalizedScore,
              detail: _irisDetail(result.face),
            ),
            BiometricScoreCard(
              label: 'Voice verification',
              value: result.voice.normalizedScore,
              detail: _voiceDetail(result.voice),
            ),
            BiometricScoreCard(
              label: 'Overall authentication',
              value: result.fusion.score,
              detail:
                  'Quality-adjusted threshold ${_percent(result.fusion.threshold)}. '
                  '${result.fusion.score >= result.fusion.threshold ? 'Passed' : 'Not met'}. '
                  'Iris weight ${_percent(result.fusion.faceWeight)}, '
                  'voice weight ${_percent(result.fusion.voiceWeight)}. '
                  'Status: ${verified ? 'VERIFIED' : result.decision}.',
            ),
          ],
        ),
        const SizedBox(height: 16),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Text(
              'Similarity values are normalized template-matching scores, not calibrated probabilities or proof of human liveness. '
              'Capture quality is shown separately. Low-quality captures request a retake; '
              'a mismatch is reported only when usable iris or voice measurements disagree with enrolled templates. '
              'Dedicated anti-spoofing is reported separately and is not currently claimed by identity matching.',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ),
        ),
        const SizedBox(height: 16),
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            SecondaryButton(
              label: verified
                  ? 'Run Another Check'
                  : (result.retryRequired
                        ? 'Retry Capture'
                        : 'Start New Check'),
              onPressed: () {
                ref.read(verificationProvider.notifier).restart();
                context.goNamed(
                  RouteNames.irl,
                  queryParameters: {
                    'flow': 'verification',
                    'user': payload.userId,
                    'eye': payload.eyeSide,
                  },
                );
              },
            ),
            SecondaryButton(
              label: 'Return Home',
              onPressed: () => context.goNamed(RouteNames.home),
            ),
          ],
        ),
      ],
    );
  }

  String _qualityDetail(VerificationResult result, bool irisCaptureOnly) {
    final parts = <String>[];
    final iris = result.face;
    if (iris.validMeasurement == false) {
      parts.add(
        'Iris capture was unavailable or unclear (quality ${_percent(iris.qualityScore ?? 0)}). '
        'Use even lighting, keep one eye in frame, and look straight at the camera.',
      );
    }
    final irisMetric = result.iris;
    if (!irisCaptureOnly && irisMetric.validMeasurement == false) {
      parts.add(
        'Iris capture ${irisMetric.irisDetected == false ? 'did not detect an iris' : 'was unclear'} '
        '(quality ${_percent(irisMetric.qualityScore ?? 0)}, minimum ${_percent(irisMetric.threshold)}). '
        'Move closer, improve lighting, and hold steady.',
      );
    }
    final voice = result.voice;
    if (voice.validMeasurement == false) {
      if (voice.speechDetected == false) {
        parts.add('No clear speech was detected. Speak the phrase out loud.');
      } else {
        parts.add(
          'Voice recording was unclear (quality ${_percent(voice.qualityScore ?? 0)}). '
          'Speak clearly in a quiet place.',
        );
      }
    }
    if (parts.isEmpty) {
      parts.add(
        'Capture confidence was inconclusive. Retake both captures with better lighting and a steady eye.',
      );
    }
    return parts.join('\n');
  }

  String _voiceDetail(VerificationMetric voice) {
    final parts = [
      'Similarity threshold ${_percent(voice.threshold)}. Capture quality '
          '${_percent(voice.qualityScore ?? 0)} / minimum '
          '${_percent(voice.qualityThreshold ?? 0)}.',
    ];
    if (voice.speechActivityScore != null && voice.activityThreshold != null) {
      parts.add(
        'Spoken activity ${_percent(voice.speechActivityScore!)} / needs ${_percent(voice.activityThreshold!)}: ${voice.speechDetected == true ? 'passed' : 'below threshold'}',
      );
    }
    return parts.join('\n');
  }

  String _irisDetail(VerificationMetric iris) {
    final availability = iris.validMeasurement == true
        ? 'Available'
        : 'Unavailable or low quality';
    return 'Score threshold ${_percent(iris.threshold)}. Status: '
        '${iris.passed ? 'PASS' : 'FAIL'}. Quality '
        '${_percent(iris.qualityScore ?? 0)} / minimum '
        '${_percent(iris.qualityThreshold ?? 0)}. $availability. '
        '${iris.sampleCount ?? 0} frames aggregated.';
  }

  String _percent(double value) => '${(value * 100).toStringAsFixed(0)}%';
}
