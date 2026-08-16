import 'package:flutter/material.dart';

class VerificationFailedPanel extends StatelessWidget {
  const VerificationFailedPanel({
    super.key,
    required this.message,
  });

  final String message;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const Icon(Icons.cancel_rounded, size: 96, color: Colors.red),
        const SizedBox(height: 16),
        const Text(
          'Verification Failed',
          style: TextStyle(fontSize: 26, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 8),
        Text(message, textAlign: TextAlign.center),
      ],
    );
  }
}
