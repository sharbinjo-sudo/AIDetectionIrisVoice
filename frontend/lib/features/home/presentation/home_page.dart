import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_names.dart';
import '../../../core/constants/app_constants.dart';
import '../../../core/theme/app_colours.dart';
import '../../../core/widgets/backend_status_badge.dart';
import '../../../core/widgets/secondary_button.dart';
import '../../../features/backend_health/providers/backend_health_provider.dart';
import '../../../shared/widgets/page_header.dart';

class HomePage extends ConsumerWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final healthAsync = ref.watch(backendHealthProvider);
    final health = healthAsync.valueOrNull;
    final serviceReachable = health?.reachable == true;
    final width = MediaQuery.sizeOf(context).width;

    return ListView(
      children: [
        _LandingHero(
          serviceReady: health?.connected == true,
          serviceReachable: serviceReachable,
        ),
        const SizedBox(height: 24),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Wrap(
              spacing: 16,
              runSpacing: 16,
              alignment: WrapAlignment.spaceBetween,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                const _SecurityStat(
                  label: 'Login Policy',
                  value: 'Credentials + Biometrics',
                  icon: Icons.lock_person_rounded,
                ),
                const _SecurityStat(
                  label: 'Identity Signals',
                  value: 'Iris + Voice',
                  icon: Icons.blur_on_rounded,
                ),
                const _SecurityStat(
                  label: 'Capture Policy',
                  value: 'Quality-aware',
                  icon: Icons.fact_check_rounded,
                ),
                SecondaryButton(
                  label: 'Open Test Mode',
                  icon: Icons.science_rounded,
                  onPressed: () => context.goNamed(RouteNames.test),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 28),
        Text(
          'Secure access in three steps',
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        const SizedBox(height: 16),
        GridView.count(
          crossAxisCount: width > 1024
              ? 3
              : width > 650
              ? 2
              : 1,
          crossAxisSpacing: 16,
          mainAxisSpacing: 16,
          mainAxisExtent: width > 650 ? 220 : 205,
          physics: const NeverScrollableScrollPhysics(),
          shrinkWrap: true,
          children: const [
            _FeatureCard(
              number: '01',
              title: 'Account credentials',
              description:
                  'Register a new profile or sign in using your customer ID and PIN.',
              icon: Icons.pin_rounded,
            ),
            _FeatureCard(
              number: '02',
              title: 'Biometric capture',
              description:
                  'Capture multiple iris frames plus clear voice segments using the local biometric service.',
              icon: Icons.fingerprint_rounded,
            ),
            _FeatureCard(
              number: '03',
              title: 'Identity decision',
              description:
                  'Quality-aware fusion compares iris and voice measurements with the templates enrolled for your account.',
              icon: Icons.shield_rounded,
            ),
          ],
        ),
        const SizedBox(height: 28),
        PageHeader(
          title: 'Local security service',
          subtitle:
              'Model readiness and backend connectivity for this installation.',
          trailing: const BackendStatusBadge(),
        ),
        const SizedBox(height: 14),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Wrap(
              spacing: 28,
              runSpacing: 14,
              children: [
                _ServiceStatus(
                  label: 'Backend',
                  ready: health?.connected == true,
                  detail: health?.connected == true
                      ? 'Connected'
                      : serviceReachable
                      ? 'Starting models'
                      : healthAsync.isLoading
                      ? 'Connecting'
                      : 'Offline',
                ),
                _ServiceStatus(
                  label: 'Voice model',
                  ready: health?.voiceModelReady == true,
                  detail: health?.voiceModelLabel ?? 'Checking',
                ),
                _ServiceStatus(
                  label: 'Iris model',
                  ready: health?.irisModelReady == true,
                  detail: health?.irisModelLabel ?? 'Checking',
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _LandingHero extends StatelessWidget {
  const _LandingHero({
    required this.serviceReady,
    required this.serviceReachable,
  });

  final bool serviceReady;
  final bool serviceReachable;

  @override
  Widget build(BuildContext context) {
    final compact = MediaQuery.sizeOf(context).width < 760;
    return DecoratedBox(
      decoration: const BoxDecoration(
        color: AppColours.deepNavy,
        borderRadius: BorderRadius.all(Radius.circular(24)),
      ),
      child: Padding(
        padding: EdgeInsets.all(compact ? 24 : 40),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  DecoratedBox(
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.10),
                      borderRadius: BorderRadius.circular(999),
                    ),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 8,
                      ),
                      child: Text(
                        serviceReady
                            ? 'Local biometric service ready'
                            : serviceReachable
                            ? 'Local biometric service starting'
                            : 'Waiting for local biometric service',
                        style: const TextStyle(color: Colors.white),
                      ),
                    ),
                  ),
                  const SizedBox(height: 22),
                  Text(
                    AppConstants.appTitle,
                    style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                      color: Colors.white,
                      height: 1.08,
                    ),
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'A general-purpose biometric authentication prototype for account login. This example uses a customer ID and PIN flow inspired by banking, with separate registration and biometric verification.',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 16,
                      height: 1.5,
                    ),
                  ),
                  const SizedBox(height: 26),
                  Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    children: [
                      FilledButton.icon(
                        onPressed: () => context.goNamed(RouteNames.login),
                        icon: const Icon(Icons.login_rounded),
                        label: const Text('Login'),
                        style: FilledButton.styleFrom(
                          backgroundColor: AppColours.primaryBlue,
                          foregroundColor: Colors.white,
                        ),
                      ),
                      OutlinedButton.icon(
                        onPressed: () => context.goNamed(RouteNames.register),
                        icon: const Icon(Icons.person_add_alt_1_rounded),
                        label: const Text('Create account'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: Colors.white,
                          side: const BorderSide(color: Colors.white70),
                          minimumSize: const Size(0, 52),
                          padding: const EdgeInsets.symmetric(
                            horizontal: 18,
                            vertical: 14,
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            if (!compact) ...[
              const SizedBox(width: 40),
              Container(
                width: 210,
                height: 210,
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.08),
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.16),
                  ),
                ),
                child: const Icon(
                  Icons.verified_user_rounded,
                  size: 92,
                  color: Colors.white,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _SecurityStat extends StatelessWidget {
  const _SecurityStat({
    required this.label,
    required this.value,
    required this.icon,
  });

  final String label;
  final String value;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 220,
      child: Row(
        children: [
          Icon(icon, color: Theme.of(context).colorScheme.primary),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: Theme.of(context).textTheme.labelLarge),
                Text(value),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _FeatureCard extends StatelessWidget {
  const _FeatureCard({
    required this.number,
    required this.title,
    required this.description,
    required this.icon,
  });

  final String number;
  final String title;
  final String description;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(22),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Icon(icon, color: Theme.of(context).colorScheme.primary),
                Text(number, style: Theme.of(context).textTheme.labelLarge),
              ],
            ),
            const SizedBox(height: 24),
            Text(title, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 10),
            Text(description),
          ],
        ),
      ),
    );
  }
}

class _ServiceStatus extends StatelessWidget {
  const _ServiceStatus({
    required this.label,
    required this.ready,
    required this.detail,
  });

  final String label;
  final bool ready;
  final String detail;

  @override
  Widget build(BuildContext context) {
    final color = ready ? AppColours.success : AppColours.warning;
    final width = MediaQuery.sizeOf(context).width;
    return SizedBox(
      width: width < 700 ? double.infinity : 260,
      child: Row(
        children: [
          Icon(
            ready ? Icons.check_circle_rounded : Icons.pending_rounded,
            color: color,
          ),
          const SizedBox(width: 10),
          Expanded(child: Text('$label: $detail')),
        ],
      ),
    );
  }
}
