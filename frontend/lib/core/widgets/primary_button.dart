import 'package:flutter/material.dart';

import '../theme/app_colours.dart';

class PrimaryButton extends StatelessWidget {
  const PrimaryButton({
    super.key,
    required this.label,
    this.onPressed,
    this.icon,
    this.expanded = false,
  });

  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;
  final bool expanded;

  @override
  Widget build(BuildContext context) {
    final child = ElevatedButton.icon(
      onPressed: onPressed,
      icon: icon == null ? const SizedBox.shrink() : Icon(icon),
      label: Text(label),
      style: ElevatedButton.styleFrom(
        backgroundColor: AppColours.deepNavy,
        foregroundColor: Colors.white,
        disabledBackgroundColor: AppColours.deepNavy.withValues(alpha: 0.45),
        disabledForegroundColor: Colors.white.withValues(alpha: 0.70),
        minimumSize: const Size(0, 52),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      ),
    );
    return expanded ? SizedBox(width: double.infinity, child: child) : child;
  }
}
