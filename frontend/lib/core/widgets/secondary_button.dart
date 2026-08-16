import 'package:flutter/material.dart';

import '../theme/app_colours.dart';

class SecondaryButton extends StatelessWidget {
  const SecondaryButton({
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
    final dark = Theme.of(context).brightness == Brightness.dark;
    final foreground = dark ? Colors.white : AppColours.primaryBlue;
    final child = OutlinedButton.icon(
      onPressed: onPressed,
      icon: icon == null ? const SizedBox.shrink() : Icon(icon),
      label: Text(label),
      style: OutlinedButton.styleFrom(
        foregroundColor: foreground,
        disabledForegroundColor: foreground.withValues(alpha: 0.55),
        backgroundColor: dark ? Colors.white.withValues(alpha: 0.10) : null,
        side: BorderSide(
          color: dark
              ? Colors.white.withValues(alpha: 0.78)
              : AppColours.primaryBlue,
        ),
        minimumSize: const Size(0, 52),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      ),
    );
    return expanded ? SizedBox(width: double.infinity, child: child) : child;
  }
}
