import 'package:flutter/material.dart';

enum RejectionType { mismatch, spoof }

class VerificationFailedPanel extends StatelessWidget {
  const VerificationFailedPanel({
    super.key,
    required this.message,
    this.retryRequired = false,
    this.qualityDetail,
    this.rejectionType,
  });

  final String message;
  final bool retryRequired;

  /// Extra, actionable guidance for quality/retry outcomes (which modality
  /// needs a retake and how to improve it).
  final String? qualityDetail;

  /// Set only when actual mismatch/spoof evidence exists; drives the
  /// "Biometric Verification Failed" styling.
  final RejectionType? rejectionType;

  @override
  Widget build(BuildContext context) {
    final isRejection = rejectionType != null;
    final heading = isRejection
        ? 'Biometric Verification Failed'
        : retryRequired
        ? 'Capture Retry Required'
        : 'Verification Incomplete';
    final color = isRejection
        ? Theme.of(context).colorScheme.error
        : Colors.orange;
    final icon = isRejection ? Icons.gpp_bad_rounded : Icons.autorenew_rounded;

    return Column(
      children: [
        Icon(icon, size: 96, color: color),
        const SizedBox(height: 16),
        Text(
          heading,
          style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 8),
        Text(message, textAlign: TextAlign.center),
        if (qualityDetail != null) ...[
          const SizedBox(height: 12),
          Text(
            qualityDetail!,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ],
    );
  }
}
