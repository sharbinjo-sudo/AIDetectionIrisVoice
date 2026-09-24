import 'package:flutter/material.dart';

class PermissionRequestCard extends StatelessWidget {
  const PermissionRequestCard({
    super.key,
    required this.title,
    required this.message,
    required this.onRequest,
    this.actionLabel = 'Grant access',
  });

  final String title;
  final String message;
  final VoidCallback onRequest;
  final String actionLabel;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            Text(message),
            const SizedBox(height: 16),
            ElevatedButton(onPressed: onRequest, child: Text(actionLabel)),
          ],
        ),
      ),
    );
  }
}
