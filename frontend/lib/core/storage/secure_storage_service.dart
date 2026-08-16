import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SecureStorageService {
  SecureStorageService([FlutterSecureStorage? storage])
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
            );

  final FlutterSecureStorage _storage;

  static const _baseUrlKey = 'base_url';
  static const _themeModeKey = 'theme_mode';

  Future<void> saveBaseUrl(String value) =>
      _storage.write(key: _baseUrlKey, value: value);

  Future<String?> readBaseUrl() => _storage.read(key: _baseUrlKey);

  Future<void> saveThemeMode(ThemeMode themeMode) =>
      _storage.write(key: _themeModeKey, value: themeMode.name);

  Future<ThemeMode> readThemeMode() async {
    final raw = await _storage.read(key: _themeModeKey);
    return ThemeMode.values.firstWhere(
      (mode) => mode.name == raw,
      orElse: () => ThemeMode.system,
    );
  }
}

final secureStorageProvider =
    Provider<SecureStorageService>((ref) => SecureStorageService());
