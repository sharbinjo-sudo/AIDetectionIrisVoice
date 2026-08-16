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
    return ListView(
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              children: [
                if (verified)
                  const VerifiedSuccessPanel()
                else
                  VerificationFailedPanel(
                    message:
                        result.failureReason ??
                        'The blink and speech challenge did not meet the required threshold.',
                  ),
                const SizedBox(height: 20),
                Text('Processing time: ${result.processingTimeMs} ms'),
                const SizedBox(height: 8),
                const Text(
                  'No biometric media or completed verification result was saved to the app.',
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        GridView.count(
          crossAxisCount: MediaQuery.sizeOf(context).width > 900 ? 3 : 1,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          crossAxisSpacing: 16,
          mainAxisSpacing: 16,
          childAspectRatio: 1.45,
          children: [
            BiometricScoreCard(
              label: 'Speech score',
              value: result.voice.normalizedScore,
              detail: _voiceDetail(result.voice),
            ),
            BiometricScoreCard(
              label: 'Blink score',
              value: result.iris.normalizedScore,
              detail: _metricDetail(result.iris, name: 'Blink'),
            ),
            BiometricScoreCard(
              label: 'Final human score',
              value: result.fusion.score,
              detail:
                  'Needs ${_percent(result.fusion.threshold)} or higher. '
                  '${result.fusion.score >= result.fusion.threshold ? 'Passed' : 'Failed'}.',
            ),
          ],
        ),
        const SizedBox(height: 16),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Text(
              'Success does not require 100%. Voice quality, spoken activity, blink quality, and the final human score each need to pass their thresholds.',
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
              label: 'Start New Check',
              onPressed: () {
                ref.read(verificationProvider.notifier).restart();
                context.goNamed(RouteNames.irl);
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

  String _voiceDetail(VerificationMetric voice) {
    final parts = [
      'Quality needs ${_percent(voice.threshold)}: ${voice.normalizedScore >= voice.threshold ? 'passed' : 'failed'}',
    ];
    if (voice.speechActivityScore != null && voice.activityThreshold != null) {
      parts.add(
        'Spoken activity ${_percent(voice.speechActivityScore!)} / needs ${_percent(voice.activityThreshold!)}: ${voice.speechDetected == true ? 'passed' : 'failed'}',
      );
    }
    return parts.join('\n');
  }

  String _metricDetail(VerificationMetric metric, {required String name}) {
    return '$name needs ${_percent(metric.threshold)} or higher. '
        '${metric.passed ? 'Passed' : 'Failed'}.';
  }

  String _percent(double value) => '${(value * 100).toStringAsFixed(0)}%';
}
