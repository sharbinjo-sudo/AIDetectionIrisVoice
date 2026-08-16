import 'package:flutter/material.dart';

class VerifiedSuccessPanel extends StatelessWidget {
  const VerifiedSuccessPanel({super.key});

  @override
  Widget build(BuildContext context) {
    return const Column(
      children: [
        Icon(Icons.verified_rounded, size: 96, color: Colors.green),
        SizedBox(height: 16),
        Text(
          'Verified as Human',
          style: TextStyle(fontSize: 26, fontWeight: FontWeight.w700),
        ),
        SizedBox(height: 8),
        Text(
          'Blink and voice checks completed successfully.',
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}
