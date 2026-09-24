import 'package:flutter/material.dart';

class VerifiedSuccessPanel extends StatelessWidget {
  const VerifiedSuccessPanel({super.key, this.irisCaptureOnly = false});

  final bool irisCaptureOnly;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Icon(Icons.verified_rounded, size: 96, color: Colors.green),
        SizedBox(height: 16),
        Text(
          'Biometric Verification Complete',
          style: TextStyle(fontSize: 26, fontWeight: FontWeight.w700),
        ),
        SizedBox(height: 8),
        Text(
          irisCaptureOnly
              ? 'Iris and voice matched the enrolled templates. Capture quality checks passed.'
              : 'Fresh iris and voice patterns matched the enrolled templates and passed capture-quality checks. This is not a dedicated liveness claim.',
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}
