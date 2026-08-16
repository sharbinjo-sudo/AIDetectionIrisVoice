import 'package:flutter/material.dart';

import '../../features/irl_verification/models/verification_step.dart';

class VerificationCheckItem extends StatelessWidget {
  const VerificationCheckItem({
    super.key,
    required this.step,
  });

  final VerificationStep step;

  @override
  Widget build(BuildContext context) {
    final icon = switch (step.status) {
      VerificationStepStatus.processing =>
        const SizedBox(
          width: 18,
          height: 18,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
      VerificationStepStatus.passed =>
        const Icon(Icons.check_circle_rounded, color: Colors.green),
      VerificationStepStatus.failed =>
        const Icon(Icons.warning_amber_rounded, color: Colors.orange),
      VerificationStepStatus.unavailable =>
        const Icon(Icons.remove_circle_outline_rounded, color: Colors.grey),
      VerificationStepStatus.pending =>
        const Icon(Icons.radio_button_unchecked_rounded, color: Colors.grey),
    };
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          icon,
          const SizedBox(width: 12),
          Expanded(child: Text(step.label)),
        ],
      ),
    );
  }
}
