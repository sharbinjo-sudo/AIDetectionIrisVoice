import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../routing/route_names.dart';

class MobileNavigationDrawer extends StatelessWidget {
  const MobileNavigationDrawer({super.key, required this.currentLocation});

  final String currentLocation;

  bool _selected(String route) => currentLocation == route;

  @override
  Widget build(BuildContext context) {
    return Drawer(
      child: ListView(
        children: [
          const DrawerHeader(
            child: Align(
              alignment: Alignment.bottomLeft,
              child: Text(
                'Advanced Human Recognition',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700),
              ),
            ),
          ),
          ListTile(
            selected: _selected('/'),
            leading: const Icon(Icons.home_rounded),
            title: const Text('Home'),
            onTap: () {
              Navigator.of(context).pop();
              context.goNamed(RouteNames.home);
            },
          ),
          ListTile(
            selected: _selected('/test'),
            leading: const Icon(Icons.science_rounded),
            title: const Text('Test'),
            onTap: () {
              Navigator.of(context).pop();
              context.goNamed(RouteNames.test);
            },
          ),
          const Divider(),
          ListTile(
            selected: _selected('/settings'),
            leading: const Icon(Icons.tune_rounded),
            title: const Text('Settings'),
            onTap: () {
              Navigator.of(context).pop();
              context.goNamed(RouteNames.settings);
            },
          ),
        ],
      ),
    );
  }
}
