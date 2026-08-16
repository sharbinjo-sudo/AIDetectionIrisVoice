import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/networking/dio_client.dart';
import '../data/backend_health_repository.dart';
import '../models/backend_health_status.dart';

final backendHealthRepositoryProvider = Provider<BackendHealthRepository>(
  (ref) => BackendHealthRepository(ref.watch(dioProvider)),
);

class BackendHealthController extends AsyncNotifier<BackendHealthStatus> {
  Timer? _retryTimer;

  @override
  Future<BackendHealthStatus> build() async {
    _retryTimer?.cancel();
    _retryTimer = Timer.periodic(const Duration(seconds: 6), (_) {
      refreshSilently();
    });
    ref.onDispose(() => _retryTimer?.cancel());
    return _fetchOrDisconnected();
  }

  Future<BackendHealthStatus> refreshStatus() async {
    state = const AsyncLoading();
    final result = await _fetchOrDisconnected();
    state = AsyncData(result);
    return result;
  }

  Future<void> refreshSilently() async {
    final result = await _fetchOrDisconnected();
    state = AsyncData(result);
  }

  Future<BackendHealthStatus> _fetchOrDisconnected() async {
    try {
      return await ref.read(backendHealthRepositoryProvider).fetch();
    } catch (_) {
      return BackendHealthStatus.disconnected();
    }
  }
}

final backendHealthProvider =
    AsyncNotifierProvider<BackendHealthController, BackendHealthStatus>(
      BackendHealthController.new,
    );
