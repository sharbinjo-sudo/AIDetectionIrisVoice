import 'package:flutter/material.dart';

import '../../models/iris_test_result.dart';

class IrisTestResultPanel extends StatelessWidget {
  const IrisTestResultPanel({
    super.key,
    required this.result,
  });

  final IrisTestResult result;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Eye detected: ${result.irisDetected ? 'Yes' : 'No'}'),
            Text('Image quality: ${_fmt(result.qualityScore)}'),
            Text('Quality score: ${_fmt(result.normalizedScore)}'),
            Text('Threshold: ${_fmt(result.threshold)}'),
            Text('Passed: ${result.passed ? 'Yes' : 'No'}'),
            Text('Processing time: ${result.processingTimeMs} ms'),
            if (result.message.isNotEmpty) Text('Backend message: ${result.message}'),
          ],
        ),
      ),
    );
  }

  String _fmt(double? value) => value == null ? 'N/A' : value.toStringAsFixed(2);
}
