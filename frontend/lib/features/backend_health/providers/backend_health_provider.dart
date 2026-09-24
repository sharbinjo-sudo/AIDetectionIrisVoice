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
  Future<void>? _refreshInFlight;

  @override
  Future<BackendHealthStatus> build() async {
    _retryTimer?.cancel();
    _retryTimer = Timer.periodic(const Duration(seconds: 3), (_) {
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
    final inFlight = _refreshInFlight;
    if (inFlight != null) {
      await inFlight;
      return;
    }
    final operation = () async {
      final result = await _fetchOrDisconnected();
      state = AsyncData(result);
    }();
    _refreshInFlight = operation;
    try {
      await operation;
    } finally {
      if (identical(_refreshInFlight, operation)) {
        _refreshInFlight = null;
      }
    }
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
