import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../routing/route_names.dart';

class MobileNavigationDrawer extends StatelessWidget {
  const MobileNavigationDrawer({
    super.key,
    required this.currentLocation,
  });

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
                'BioFusion AI',
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
          ListTile(
            selected: _selected('/irl'),
            leading: const Icon(Icons.verified_rounded),
            title: const Text('IRL'),
            onTap: () {
              Navigator.of(context).pop();
              context.goNamed(RouteNames.irl);
            },
          ),
        ],
      ),
    );
  }
}
