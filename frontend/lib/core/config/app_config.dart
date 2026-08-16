import 'package:flutter/foundation.dart';

class AppConfig {
  const AppConfig._();

  static const String appName = 'BioFusion AI';
  static const String subtitle = 'Voice and Iris Identity Verification';
  static const String androidEmulatorBaseUrl = 'http://10.0.2.2:8000/api/v1';
  static const String localDesktopBaseUrl = 'http://127.0.0.1:8000/api/v1';
  static const Duration connectTimeout = Duration(seconds: 45);
  static const Duration receiveTimeout = Duration(seconds: 45);

  static String get defaultBaseUrl {
    if (kIsWeb) {
      return localDesktopBaseUrl;
    }

    return switch (defaultTargetPlatform) {
      TargetPlatform.android => androidEmulatorBaseUrl,
      TargetPlatform.iOS => localDesktopBaseUrl,
      TargetPlatform.macOS => localDesktopBaseUrl,
      TargetPlatform.windows => localDesktopBaseUrl,
      TargetPlatform.linux => localDesktopBaseUrl,
      TargetPlatform.fuchsia => localDesktopBaseUrl,
    };
  }

  static String normalizeBaseUrl(String baseUrl) {
    final trimmed = baseUrl.trim();
    if (trimmed.isEmpty) {
      return defaultBaseUrl;
    }

    final looksLikeAndroidEmulator = trimmed.startsWith(androidEmulatorBaseUrl);
    final runningOnDesktop =
        !kIsWeb &&
        {
          TargetPlatform.windows,
          TargetPlatform.macOS,
          TargetPlatform.linux,
          TargetPlatform.iOS,
          TargetPlatform.fuchsia,
        }.contains(defaultTargetPlatform);

    if (looksLikeAndroidEmulator && runningOnDesktop) {
      return trimmed.replaceFirst('10.0.2.2', '127.0.0.1');
    }

    return trimmed;
  }
}
