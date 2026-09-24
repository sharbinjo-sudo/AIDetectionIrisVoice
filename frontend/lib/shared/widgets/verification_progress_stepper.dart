import 'package:flutter/material.dart';

import '../../features/irl_verification/models/verification_step.dart';
import 'verification_check_item.dart';

class VerificationProgressStepper extends StatelessWidget {
  const VerificationProgressStepper({super.key, required this.steps});

  final List<VerificationStep> steps;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Verification checklist',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 12),
            for (final step in steps) VerificationCheckItem(step: step),
          ],
        ),
      ),
    );
  }
}
