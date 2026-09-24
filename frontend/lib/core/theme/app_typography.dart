import 'package:flutter/material.dart';

class AppTypography {
  const AppTypography._();

  static TextTheme lightTextTheme() => Typography.material2021().black.copyWith(
    headlineLarge: const TextStyle(
      fontSize: 44,
      fontWeight: FontWeight.w700,
      height: 1.05,
    ),
    headlineMedium: const TextStyle(fontSize: 34, fontWeight: FontWeight.w700),
    titleLarge: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
  );
}
