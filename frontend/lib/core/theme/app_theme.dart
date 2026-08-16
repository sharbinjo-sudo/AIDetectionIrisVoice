import 'package:flutter/material.dart';

import 'app_colours.dart';
import 'app_typography.dart';

class AppTheme {
  const AppTheme._();

  static ThemeData light() {
    final scheme = ColorScheme.fromSeed(
      seedColor: AppColours.primaryBlue,
      brightness: Brightness.light,
      primary: AppColours.primaryBlue,
      secondary: AppColours.brightBlue,
      surface: Colors.white,
      error: AppColours.error,
    );

    return ThemeData(
      useMaterial3: true,
      splashFactory: InkRipple.splashFactory,
      colorScheme: scheme,
      scaffoldBackgroundColor: AppColours.lightBackground,
      textTheme: AppTypography.lightTextTheme().apply(
        bodyColor: AppColours.text,
        displayColor: AppColours.deepNavy,
      ),
      cardTheme: CardThemeData(
        color: Colors.white,
        elevation: 2,
        shadowColor: Colors.black.withValues(alpha: 0.05),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: _elevatedButtonStyle(dark: false),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: _filledButtonStyle(dark: false),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: _outlinedButtonStyle(dark: false),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(foregroundColor: AppColours.primaryBlue),
      ),
      segmentedButtonTheme: SegmentedButtonThemeData(
        style: _segmentedButtonStyle(dark: false),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: const BorderSide(color: AppColours.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: const BorderSide(color: AppColours.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: const BorderSide(color: AppColours.primaryBlue),
        ),
      ),
    );
  }

  static ThemeData dark() {
    final scheme = ColorScheme.fromSeed(
      seedColor: AppColours.brightBlue,
      brightness: Brightness.dark,
      primary: AppColours.brightBlue,
      secondary: AppColours.cyan,
      surface: AppColours.darkSurface,
      error: AppColours.error,
    );

    return ThemeData(
      useMaterial3: true,
      splashFactory: InkRipple.splashFactory,
      colorScheme: scheme,
      scaffoldBackgroundColor: AppColours.darkBackground,
      textTheme: AppTypography.lightTextTheme().apply(
        bodyColor: AppColours.darkText,
        displayColor: AppColours.darkText,
      ),
      cardTheme: CardThemeData(
        color: AppColours.darkSurface,
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: _elevatedButtonStyle(dark: true),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: _filledButtonStyle(dark: true),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: _outlinedButtonStyle(dark: true),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(foregroundColor: AppColours.darkText),
      ),
      segmentedButtonTheme: SegmentedButtonThemeData(
        style: _segmentedButtonStyle(dark: true),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppColours.darkElevated,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: const BorderSide(color: AppColours.darkElevated),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: const BorderSide(color: AppColours.darkElevated),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: const BorderSide(color: AppColours.cyan),
        ),
      ),
    );
  }

  static ButtonStyle _elevatedButtonStyle({required bool dark}) {
    return ElevatedButton.styleFrom(
      minimumSize: const Size(0, 52),
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
      backgroundColor: dark ? AppColours.deepNavy : AppColours.primaryBlue,
      foregroundColor: Colors.white,
      disabledBackgroundColor: dark
          ? AppColours.darkElevated
          : AppColours.border,
      disabledForegroundColor: dark
          ? AppColours.darkMuted
          : AppColours.text.withValues(alpha: 0.55),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
    );
  }

  static ButtonStyle _filledButtonStyle({required bool dark}) {
    return FilledButton.styleFrom(
      minimumSize: const Size(0, 52),
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
      backgroundColor: dark ? AppColours.brightBlue : AppColours.primaryBlue,
      foregroundColor: Colors.white,
      disabledBackgroundColor: dark
          ? AppColours.darkElevated
          : AppColours.border,
      disabledForegroundColor: dark
          ? AppColours.darkMuted
          : AppColours.text.withValues(alpha: 0.55),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
    );
  }

  static ButtonStyle _outlinedButtonStyle({required bool dark}) {
    final foreground = dark ? AppColours.darkText : AppColours.primaryBlue;
    final disabledForeground = dark
        ? AppColours.darkMuted
        : AppColours.text.withValues(alpha: 0.55);

    return OutlinedButton.styleFrom(
      minimumSize: const Size(0, 52),
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
      foregroundColor: foreground,
      disabledForegroundColor: disabledForeground,
      backgroundColor: dark ? Colors.white.withValues(alpha: 0.06) : null,
      side: BorderSide(
        color: dark ? AppColours.darkMuted : AppColours.primaryBlue,
      ),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
    );
  }

  static ButtonStyle _segmentedButtonStyle({required bool dark}) {
    return ButtonStyle(
      foregroundColor: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.disabled)) {
          return dark
              ? AppColours.darkMuted
              : AppColours.text.withValues(alpha: 0.45);
        }
        if (states.contains(WidgetState.selected)) {
          return Colors.white;
        }
        return dark ? AppColours.darkText : AppColours.primaryBlue;
      }),
      backgroundColor: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return dark ? AppColours.brightBlue : AppColours.primaryBlue;
        }
        return dark ? Colors.white.withValues(alpha: 0.04) : Colors.transparent;
      }),
      side: WidgetStateProperty.resolveWith((states) {
        final color = states.contains(WidgetState.selected)
            ? (dark ? AppColours.brightBlue : AppColours.primaryBlue)
            : (dark ? AppColours.darkMuted : AppColours.border);
        return BorderSide(color: color);
      }),
    );
  }
}
