import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/config/app_config.dart';
import '../../../core/storage/secure_storage_service.dart';

class SettingsState {
  const SettingsState({required this.baseUrl, required this.themeMode});

  final String baseUrl;
  final ThemeMode themeMode;

  SettingsState copyWith({String? baseUrl, ThemeMode? themeMode}) {
    return SettingsState(
      baseUrl: baseUrl ?? this.baseUrl,
      themeMode: themeMode ?? this.themeMode,
    );
  }

  factory SettingsState.initial() {
    return SettingsState(
      baseUrl: AppConfig.defaultBaseUrl,
      themeMode: ThemeMode.system,
    );
  }
}

class SettingsController extends Notifier<SettingsState> {
  @override
  SettingsState build() {
    final storage = ref.read(secureStorageProvider);
    Future<void>.microtask(() async {
      final storedBaseUrl = await storage.readBaseUrl();
      final baseUrl = AppConfig.normalizeBaseUrl(
        storedBaseUrl ?? state.baseUrl,
      );
      final themeMode = await storage.readThemeMode();
      if (storedBaseUrl != baseUrl) {
        await storage.saveBaseUrl(baseUrl);
      }
      state = state.copyWith(baseUrl: baseUrl, themeMode: themeMode);
    });
    return SettingsState.initial();
  }

  Future<void> setBaseUrl(String baseUrl) async {
    final storage = ref.read(secureStorageProvider);
    final normalizedBaseUrl = AppConfig.normalizeBaseUrl(baseUrl);
    await storage.saveBaseUrl(normalizedBaseUrl);
    state = state.copyWith(baseUrl: normalizedBaseUrl);
  }

  Future<void> toggleTheme() async {
    final nextTheme = switch (state.themeMode) {
      ThemeMode.light => ThemeMode.dark,
      ThemeMode.dark => ThemeMode.light,
      ThemeMode.system => ThemeMode.dark,
    };
    await setThemeMode(nextTheme);
  }

  Future<void> setThemeMode(ThemeMode themeMode) async {
    final storage = ref.read(secureStorageProvider);
    await storage.saveThemeMode(themeMode);
    state = state.copyWith(themeMode: themeMode);
  }
}

final settingsProvider = NotifierProvider<SettingsController, SettingsState>(
  SettingsController.new,
);
