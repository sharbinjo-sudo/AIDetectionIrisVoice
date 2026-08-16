import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../constants/app_constants.dart';
import '../routing/route_names.dart';
import '../theme/app_colours.dart';
import '../../features/settings/providers/settings_provider.dart';
import 'backend_status_badge.dart';

class ResponsiveNavbar extends ConsumerWidget implements PreferredSizeWidget {
  const ResponsiveNavbar({
    super.key,
    required this.currentLocation,
    this.onMenuPressed,
  });

  final String currentLocation;
  final VoidCallback? onMenuPressed;

  bool _selected(String route) => currentLocation == route;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final width = MediaQuery.sizeOf(context).width;
    final mobile = width < AppConstants.mobileBreakpoint;

    return AppBar(
      titleSpacing: 20,
      leading: mobile
          ? IconButton(
              onPressed: onMenuPressed,
              icon: const Icon(Icons.menu_rounded),
            )
          : null,
      title: Row(
        children: [
          Container(
            width: 34,
            height: 34,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              color: AppColours.primaryBlue,
            ),
            child: const Icon(Icons.verified_user_rounded, color: Colors.white),
          ),
          const SizedBox(width: 12),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: const [
              Text('BioFusion AI', style: TextStyle(fontWeight: FontWeight.w700)),
              Text(
                'Voice and Iris Identity Verification',
                style: TextStyle(fontSize: 12),
              ),
            ],
          ),
        ],
      ),
      actions: [
        if (!mobile) ...[
          _NavItem(
            label: 'Home',
            selected: _selected('/'),
            onTap: () => context.goNamed(RouteNames.home),
          ),
          _NavItem(
            label: 'Test',
            selected: _selected('/test'),
            onTap: () => context.goNamed(RouteNames.test),
          ),
          _NavItem(
            label: 'IRL',
            selected: _selected('/irl'),
            onTap: () => context.goNamed(RouteNames.irl),
          ),
          const SizedBox(width: 8),
        ],
        const BackendStatusBadge(),
        const SizedBox(width: 8),
        IconButton(
          tooltip: 'Toggle theme',
          onPressed: () => ref.read(settingsProvider.notifier).toggleTheme(),
          icon: const Icon(Icons.contrast_rounded),
        ),
        IconButton(
          tooltip: 'Settings',
          onPressed: () => context.goNamed(RouteNames.settings),
          icon: const Icon(Icons.tune_rounded),
        ),
        const SizedBox(width: 8),
      ],
    );
  }

  @override
  Size get preferredSize => const Size.fromHeight(72);
}

class _NavItem extends StatelessWidget {
  const _NavItem({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      child: TextButton(
        onPressed: onTap,
        style: TextButton.styleFrom(
          foregroundColor: selected
              ? Theme.of(context).colorScheme.primary
              : Theme.of(context).textTheme.bodyMedium?.color,
        ),
        child: Text(label),
      ),
    );
  }
}
