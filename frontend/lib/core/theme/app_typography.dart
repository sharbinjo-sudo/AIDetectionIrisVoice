import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class AppTypography {
  const AppTypography._();

  static TextTheme lightTextTheme() =>
      GoogleFonts.spaceGroteskTextTheme().copyWith(
        headlineLarge: GoogleFonts.spaceGrotesk(
          fontSize: 44,
          fontWeight: FontWeight.w700,
          height: 1.05,
        ),
        headlineMedium: GoogleFonts.spaceGrotesk(
          fontSize: 34,
          fontWeight: FontWeight.w700,
        ),
        titleLarge: GoogleFonts.spaceGrotesk(
          fontSize: 22,
          fontWeight: FontWeight.w700,
        ),
      );
}
