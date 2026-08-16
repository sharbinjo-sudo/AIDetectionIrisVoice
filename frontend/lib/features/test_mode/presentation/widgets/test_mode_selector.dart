import 'package:flutter/material.dart';

enum TestPanelType { iris, voice }

class TestModeSelector extends StatelessWidget {
  const TestModeSelector({
    super.key,
    required this.selected,
    required this.onSelected,
    required this.stacked,
  });

  final TestPanelType selected;
  final ValueChanged<TestPanelType> onSelected;
  final bool stacked;

  @override
  Widget build(BuildContext context) {
    if (stacked) {
      return Column(
        children: [
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: () => onSelected(TestPanelType.iris),
              child: const Text('Test Iris Camera'),
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton(
              onPressed: () => onSelected(TestPanelType.voice),
              child: const Text('Test Voice Recognition'),
            ),
          ),
        ],
      );
    }

    return SegmentedButton<TestPanelType>(
      segments: const [
        ButtonSegment(
          value: TestPanelType.iris,
          label: Text('Test Iris Camera'),
          icon: Icon(Icons.visibility_rounded),
        ),
        ButtonSegment(
          value: TestPanelType.voice,
          label: Text('Test Voice Recognition'),
          icon: Icon(Icons.graphic_eq_rounded),
        ),
      ],
      selected: {selected},
      onSelectionChanged: (value) => onSelected(value.first),
    );
  }
}
