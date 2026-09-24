import 'package:flutter/material.dart';

class BiometricScoreCard extends StatelessWidget {
  const BiometricScoreCard({
    super.key,
    required this.label,
    required this.value,
    this.detail,
    this.valueLabel,
  });

  final String label;
  final double value;
  final String? detail;
  final String? valueLabel;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            Text(
              valueLabel ?? '${(value * 100).toStringAsFixed(1)}%',
              style: Theme.of(
                context,
              ).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w700),
            ),
            if (detail != null) ...[const SizedBox(height: 8), Text(detail!)],
          ],
        ),
      ),
    );
  }
}
