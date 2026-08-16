import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/constants/app_constants.dart';
import '../../../core/routing/route_names.dart';
import '../../../core/widgets/backend_status_badge.dart';
import '../../../core/widgets/primary_button.dart';
import '../../../core/widgets/secondary_button.dart';
import '../../../features/backend_health/providers/backend_health_provider.dart';
import '../../../shared/widgets/page_header.dart';

class HomePage extends ConsumerWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final health = ref.watch(backendHealthProvider).valueOrNull;
    final width = MediaQuery.sizeOf(context).width;

    return ListView(
      children: [
        Container(
          padding: const EdgeInsets.all(28),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(28),
            gradient: LinearGradient(
              colors: [
                Theme.of(context).colorScheme.primary.withValues(alpha: 0.95),
                Theme.of(context).colorScheme.secondary.withValues(alpha: 0.9),
              ],
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Privacy-First Human Verification\nPowered by Voice and Blink AI',
                style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                      color: Colors.white,
                    ),
              ),
              const SizedBox(height: 16),
              const Text(
                'Check that a real human is present using an eye challenge, a spoken response, and score-level fusion.',
                style: TextStyle(color: Colors.white, fontSize: 16),
              ),
              const SizedBox(height: 24),
              Wrap(
                spacing: 12,
                runSpacing: 12,
                children: [
                  PrimaryButton(
                    label: 'Start IRL Verification',
                    icon: Icons.verified_user_rounded,
                    onPressed: () => context.goNamed(RouteNames.irl),
                  ),
                  SecondaryButton(
                    label: 'Open Test Mode',
                    icon: Icons.science_rounded,
                    onPressed: () => context.goNamed(RouteNames.test),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),
        GridView.count(
          crossAxisCount: width > 1024 ? 3 : width > 600 ? 2 : 1,
          crossAxisSpacing: 16,
          mainAxisSpacing: 16,
          childAspectRatio: 1.35,
          physics: const NeverScrollableScrollPhysics(),
          shrinkWrap: true,
          children: const [
            _FeatureCard(
              title: 'Voice Challenge',
              lines: [
                'Spoken-response quality check',
                'Temporary audio processing only',
              ],
              icon: Icons.graphic_eq_rounded,
            ),
            _FeatureCard(
              title: 'Blink Challenge',
              lines: [
                'Open-eye and blink capture flow',
                'Temporary eye-frame analysis',
              ],
              icon: Icons.visibility_rounded,
            ),
            _FeatureCard(
              title: 'Human Fusion',
              lines: [
                'Combines voice and blink signals',
                'Produces one final human score',
              ],
              icon: Icons.merge_type_rounded,
            ),
          ],
        ),
        const SizedBox(height: 24),
        PageHeader(
          title: 'System Status',
          subtitle:
              'Backend connectivity and model readiness for the current local environment.',
          trailing: const BackendStatusBadge(),
        ),
        const SizedBox(height: 16),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Backend connected: ${health?.connected == true ? 'Yes' : 'No'}'),
                Text(
                  'Voice engine: ${health?.voiceModelReady == true ? 'Ready' : 'Not ready'}'
                  '${health == null ? '' : ' (${health.voiceModelMode})'}',
                ),
                Text(
                  'Blink engine: ${health?.irisModelReady == true ? 'Ready' : 'Not ready'}'
                  '${health == null ? '' : ' (${health.irisModelMode})'}',
                ),
                Text('Development thresholds: ${health?.developmentThresholds == true ? 'Warning' : 'Disabled'}'),
              ],
            ),
          ),
        ),
        const SizedBox(height: 24),
        const Card(
          child: Padding(
            padding: EdgeInsets.all(18),
            child: Text(AppConstants.phaseOneNote),
          ),
        ),
        const SizedBox(height: 24),
        const Card(
          child: Padding(
            padding: EdgeInsets.all(18),
            child: Text('Capture -> Blink -> Speak -> Score -> Verify'),
          ),
        ),
      ],
    );
  }
}

class _FeatureCard extends StatelessWidget {
  const _FeatureCard({
    required this.title,
    required this.lines,
    required this.icon,
  });

  final String title;
  final List<String> lines;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon),
            const SizedBox(height: 16),
            Text(title, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            for (final line in lines)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text('- $line'),
              ),
          ],
        ),
      ),
    );
  }
}
