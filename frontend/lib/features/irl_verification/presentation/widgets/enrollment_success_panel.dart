import 'package:flutter/material.dart';

/// Shown only after the enrollment API confirms that templates were saved.
class EnrollmentSuccessPanel extends StatelessWidget {
  const EnrollmentSuccessPanel({
    super.key,
    required this.onLogin,
    required this.onHome,
  });

  final VoidCallback onLogin;
  final VoidCallback onHome;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(vertical: 32),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 620),
          child: Card(
            child: Padding(
              padding: const EdgeInsets.all(28),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TweenAnimationBuilder<double>(
                    tween: Tween(begin: 0.8, end: 1),
                    duration: MediaQuery.disableAnimationsOf(context)
                        ? Duration.zero
                        : const Duration(milliseconds: 350),
                    curve: Curves.easeOutCubic,
                    builder: (context, scale, child) =>
                        Transform.scale(scale: scale, child: child),
                    child: Container(
                      width: 96,
                      height: 96,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: theme.colorScheme.primaryContainer,
                      ),
                      child: Icon(
                        Icons.check_rounded,
                        size: 58,
                        color: theme.colorScheme.onPrimaryContainer,
                        semanticLabel: 'Enrollment successful',
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                  Semantics(
                    liveRegion: true,
                    header: true,
                    child: Text(
                      'Registration complete',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.headlineMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'Your biometric enrollment was saved successfully.',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.titleMedium,
                  ),
                  const SizedBox(height: 12),
                  const Text(
                    'You can now log in with your customer ID and PIN, '
                    'then complete biometric verification to access your account.',
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 28),
                  Wrap(
                    alignment: WrapAlignment.center,
                    spacing: 12,
                    runSpacing: 12,
                    children: [
                      FilledButton.icon(
                        onPressed: onLogin,
                        icon: const Icon(Icons.login_rounded),
                        label: const Text('Go to Login'),
                      ),
                      OutlinedButton.icon(
                        onPressed: onHome,
                        icon: const Icon(Icons.home_outlined),
                        label: const Text('Return Home'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
