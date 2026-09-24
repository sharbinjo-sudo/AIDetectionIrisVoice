import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../features/backend_health/providers/backend_health_provider.dart';
import '../theme/app_colours.dart';

class BackendStatusBadge extends ConsumerWidget {
  const BackendStatusBadge({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final health = ref.watch(backendHealthProvider);
    final status = health.valueOrNull;
    final connected = status?.connected == true;
    final reachable = status?.reachable == true;
    final checking = health.isLoading && status == null;
    final colour = connected ? AppColours.success : AppColours.warning;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: colour.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: colour.withValues(alpha: 0.35)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.circle, size: 10, color: colour),
          const SizedBox(width: 8),
          Text(
            checking
                ? 'Connecting to Backend…'
                : connected
                ? 'Backend Connected'
                : reachable
                ? 'Backend Starting'
                : 'Backend Offline',
            style: TextStyle(color: colour, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}
