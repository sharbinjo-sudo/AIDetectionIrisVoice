import 'package:flutter/material.dart';

class VoiceWaveform extends StatefulWidget {
  const VoiceWaveform({
    super.key,
    required this.amplitude,
    required this.active,
  });

  final double amplitude;
  final bool active;

  @override
  State<VoiceWaveform> createState() => _VoiceWaveformState();
}

class _VoiceWaveformState extends State<VoiceWaveform> {
  static const _barCount = 32;
  // The rolling waveform removes the oldest bar and appends the newest one,
  // so this list must be growable. List.filled defaults to a fixed-length
  // list, which caused Flutter web to throw `Unsupported operation: removeAt`.
  late final List<double> _levels = List<double>.filled(
    _barCount,
    0.04,
    growable: true,
  );

  @override
  void didUpdateWidget(covariant VoiceWaveform oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.active) {
      _levels.removeAt(0);
      _levels.add(widget.amplitude.clamp(0.04, 1.0).toDouble());
    } else if (oldWidget.active) {
      _levels.fillRange(0, _levels.length, 0.04);
    }
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final available = constraints.maxWidth.isFinite
            ? constraints.maxWidth
            : 240.0;
        final barWidth = ((available - (_barCount * 3.0)) / _barCount)
            .clamp(1.0, 4.0)
            .toDouble();
        final sidePadding = ((available - (_barCount * barWidth)) /
                (_barCount * 2))
            .clamp(0.0, 1.5)
            .toDouble();
        return SizedBox(
          height: 60,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: _levels
                .map(
                  (level) => Padding(
                    padding: EdgeInsets.symmetric(horizontal: sidePadding),
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 90),
                      curve: Curves.easeOut,
                      width: barWidth,
                      height: 8 + (level * 48),
                      decoration: BoxDecoration(
                        color: Theme.of(context).colorScheme.primary.withValues(
                          alpha: widget.active ? 0.95 : 0.35,
                        ),
                        borderRadius: BorderRadius.circular(999),
                      ),
                    ),
                  ),
                )
                .toList(),
          ),
        );
      },
    );
  }
}
