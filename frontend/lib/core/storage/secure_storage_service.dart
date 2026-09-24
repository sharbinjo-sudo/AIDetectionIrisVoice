import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SecureStorageService {
  SecureStorageService([FlutterSecureStorage? storage])
    : _storage =
          storage ??
          const FlutterSecureStorage(
            aOptions: AndroidOptions(encryptedSharedPreferences: true),
          );

  final FlutterSecureStorage _storage;
  String? _cachedBankingSessionToken;
  bool _bankingSessionTokenLoaded = false;

  static const _baseUrlKey = 'base_url';
  static const _themeModeKey = 'theme_mode';
  static const _bankingSessionTokenKey = 'banking_session_token';
  static const _bankingCustomerIdKey = 'banking_customer_id';
  static const _biometricUserIdKey = 'biometric_user_id';

  Future<void> saveBaseUrl(String value) =>
      _storage.write(key: _baseUrlKey, value: value);

  Future<String?> readBaseUrl() => _storage.read(key: _baseUrlKey);

  Future<void> saveThemeMode(ThemeMode themeMode) =>
      _storage.write(key: _themeModeKey, value: themeMode.name);

  Future<void> saveBankingSession({
    required String token,
    required String customerId,
    required String biometricUserId,
  }) async {
    await _storage.write(key: _bankingSessionTokenKey, value: token);
    await _storage.write(key: _bankingCustomerIdKey, value: customerId);
    await _storage.write(key: _biometricUserIdKey, value: biometricUserId);
    _cachedBankingSessionToken = token;
    _bankingSessionTokenLoaded = true;
  }

  Future<String?> readBankingSessionToken() async {
    if (_bankingSessionTokenLoaded) return _cachedBankingSessionToken;
    _cachedBankingSessionToken = await _storage.read(
      key: _bankingSessionTokenKey,
    );
    _bankingSessionTokenLoaded = true;
    return _cachedBankingSessionToken;
  }

  Future<String?> readBankingCustomerId() =>
      _storage.read(key: _bankingCustomerIdKey);

  Future<String?> readBiometricUserId() =>
      _storage.read(key: _biometricUserIdKey);

  Future<ThemeMode> readThemeMode() async {
    final raw = await _storage.read(key: _themeModeKey);
    return ThemeMode.values.firstWhere(
      (mode) => mode.name == raw,
      orElse: () => ThemeMode.system,
    );
  }
}

final secureStorageProvider = Provider<SecureStorageService>(
  (ref) => SecureStorageService(),
);
