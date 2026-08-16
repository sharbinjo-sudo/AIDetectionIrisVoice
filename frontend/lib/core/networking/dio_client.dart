import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../config/app_config.dart';
import '../../features/settings/providers/settings_provider.dart';
import 'auth_interceptor.dart';

final dioProvider = Provider<Dio>((ref) {
  final settings = ref.watch(settingsProvider);
  final client = Dio(
    BaseOptions(
      baseUrl: settings.baseUrl,
      connectTimeout: AppConfig.connectTimeout,
      receiveTimeout: AppConfig.receiveTimeout,
    ),
  );
  client.interceptors.add(const AuthInterceptor());
  if (kDebugMode) {
    client.interceptors.add(
      LogInterceptor(
        requestBody: true,
        responseBody: false,
      ),
    );
  }
  return client;
});
