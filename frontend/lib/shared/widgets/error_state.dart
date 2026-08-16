import 'package:flutter/material.dart';

import '../../core/widgets/error_panel.dart';

class ErrorState extends StatelessWidget {
  const ErrorState({
    super.key,
    required this.message,
    this.onRetry,
  });

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return ErrorPanel(message: message, onRetry: onRetry);
  }
}
