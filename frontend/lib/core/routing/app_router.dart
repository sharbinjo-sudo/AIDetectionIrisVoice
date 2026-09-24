import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/home/presentation/home_page.dart';
import '../../features/home/presentation/banking_auth_page.dart';
import '../../features/irl_verification/presentation/irl_page.dart';
import '../../features/irl_verification/presentation/verification_result_page.dart';
import '../../features/settings/presentation/settings_page.dart';
import '../../features/test_mode/presentation/test_page.dart';
import '../../shared/models/result_navigation_payload.dart';
import '../widgets/app_scaffold.dart';
import 'route_names.dart';

final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/',
    routes: [
      ShellRoute(
        builder: (context, state, child) =>
            AppScaffold(currentLocation: state.uri.path, child: child),
        routes: [
          GoRoute(
            path: '/',
            name: RouteNames.home,
            builder: (context, state) => const HomePage(),
          ),
          GoRoute(
            path: '/login',
            name: RouteNames.login,
            builder: (context, state) => const BankingAuthPage.login(),
          ),
          GoRoute(
            path: '/register',
            name: RouteNames.register,
            builder: (context, state) => const BankingAuthPage.register(),
          ),
          GoRoute(
            path: '/test',
            name: RouteNames.test,
            builder: (context, state) => const TestPage(),
          ),
          GoRoute(
            path: '/irl',
            name: RouteNames.irl,
            redirect: (context, state) {
              final flow = state.uri.queryParameters['flow'];
              final userId = state.uri.queryParameters['user'];
              final validFlow = flow == 'enrollment' || flow == 'verification';
              return validFlow && userId != null && userId.isNotEmpty
                  ? null
                  : '/';
            },
            builder: (context, state) => IrlPage(
              flow: state.uri.queryParameters['flow']!,
              userId: state.uri.queryParameters['user'],
              initialEyeSide: state.uri.queryParameters['eye'],
            ),
            routes: [
              GoRoute(
                path: 'result',
                name: RouteNames.irlResult,
                redirect: (context, state) =>
                    state.extra is ResultNavigationPayload ? null : '/irl',
                builder: (context, state) => VerificationResultPage(
                  payload: state.extra! as ResultNavigationPayload,
                ),
              ),
            ],
          ),
          GoRoute(
            path: '/settings',
            name: RouteNames.settings,
            builder: (context, state) => const SettingsPage(),
          ),
        ],
      ),
    ],
  );
});
