import 'package:flutter/foundation.dart';

class AppConfig {
  const AppConfig._();

  static const String appName = 'Advanced Human Recognition';
  static const String subtitle = 'Using AI and Multibiometric Authentication';
  static const String androidEmulatorBaseUrl = 'http://10.0.2.2:8000/api/v1';
  static const String localDesktopBaseUrl = 'http://127.0.0.1:8000/api/v1';
  static const String configuredBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
  );
  static const Duration connectTimeout = Duration(seconds: 45);
  static const Duration receiveTimeout = Duration(seconds: 45);

  static String get defaultBaseUrl {
    final configured = configuredBaseUrl.trim();
    if (configured.isNotEmpty && validateBaseUrl(configured) == null) {
      return _withApiPath(configured);
    }
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

    var normalized = looksLikeAndroidEmulator && runningOnDesktop
        ? trimmed.replaceFirst('10.0.2.2', '127.0.0.1')
        : trimmed;
    if (validateBaseUrl(normalized) != null) {
      return defaultBaseUrl;
    }
    return _withApiPath(normalized);
  }

  static String? validateBaseUrl(String? value) {
    final input = value?.trim() ?? '';
    if (input.isEmpty) return null;
    final uri = Uri.tryParse(input);
    if (uri == null ||
        !{'http', 'https'}.contains(uri.scheme.toLowerCase()) ||
        uri.host.isEmpty) {
      return 'Enter a complete HTTP URL, for example http://127.0.0.1:8000/api/v1';
    }
    if (uri.hasQuery || uri.hasFragment) {
      return 'Backend URL cannot contain a query or fragment.';
    }
    return null;
  }

  static String _withApiPath(String value) {
    var normalized = value.trim();
    while (normalized.endsWith('/')) {
      normalized = normalized.substring(0, normalized.length - 1);
    }
    final uri = Uri.tryParse(normalized);
    if (uri != null && (uri.path.isEmpty || uri.path == '/')) {
      return uri.replace(path: '/api/v1').toString();
    }
    return normalized;
  }
}
