import 'package:flutter/material.dart';

import '../../models/voice_test_result.dart';

class VoiceTestResultPanel extends StatelessWidget {
  const VoiceTestResultPanel({super.key, required this.result});

  final VoiceTestResult result;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Recording duration: ${_fmt(result.durationSeconds)} s'),
            Text('Speech detected: ${result.speechDetected ? 'Yes' : 'No'}'),
            Text('Speech activity: ${_fmt(result.speechActivityScore)}'),
            Text('Mic RMS level: ${_fmt(result.rmsLevel)}'),
            Text('Mic peak level: ${_fmt(result.peakLevel)}'),
            Text('Speech quality: ${_fmt(result.qualityScore)}'),
            Text('Speech score: ${_fmt(result.normalizedScore)}'),
            Text('Threshold: ${_fmt(result.threshold)}'),
            Text('Passed: ${result.passed ? 'Yes' : 'No'}'),
            Text('Processing time: ${result.processingTimeMs} ms'),
            if (result.message.isNotEmpty)
              Text('Backend message: ${result.message}'),
          ],
        ),
      ),
    );
  }

  String _fmt(double? value) =>
      value == null ? 'N/A' : value.toStringAsFixed(2);
}
