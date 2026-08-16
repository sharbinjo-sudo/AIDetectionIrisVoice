import 'package:flutter/material.dart';

import '../constants/app_constants.dart';
import 'mobile_navigation_drawer.dart';
import 'responsive_navbar.dart';

class AppScaffold extends StatelessWidget {
  const AppScaffold({
    super.key,
    required this.currentLocation,
    required this.child,
  });

  final String currentLocation;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final useDrawer = width < AppConstants.mobileBreakpoint;
    final scaffoldKey = GlobalKey<ScaffoldState>();

    return Scaffold(
      key: scaffoldKey,
      appBar: ResponsiveNavbar(
        currentLocation: currentLocation,
        onMenuPressed: useDrawer
            ? () => scaffoldKey.currentState?.openDrawer()
            : null,
      ),
      drawer: useDrawer
          ? MobileNavigationDrawer(currentLocation: currentLocation)
          : null,
      body: SafeArea(
        child: Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1280),
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: child,
            ),
          ),
        ),
      ),
    );
  }
}
