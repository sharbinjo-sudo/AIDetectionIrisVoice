import 'package:flutter/material.dart';

class VoiceWaveform extends StatelessWidget {
  const VoiceWaveform({
    super.key,
    required this.amplitude,
    required this.active,
  });

  final double amplitude;
  final bool active;

  @override
  Widget build(BuildContext context) {
    final bars = List.generate(
      18,
      (index) => (active ? amplitude : 0.05) * ((index % 5) + 1),
    );
    return SizedBox(
      height: 60,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: bars
            .map(
              (value) => Padding(
                padding: const EdgeInsets.symmetric(horizontal: 2),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 160),
                  width: 6,
                  height: 14 + (value * 26),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.primary,
                    borderRadius: BorderRadius.circular(999),
                  ),
                ),
              ),
            )
            .toList(),
      ),
    );
  }
}
