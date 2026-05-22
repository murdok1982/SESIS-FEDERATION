import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'colors.dart';

class AppTheme {
  AppTheme._();

  static ThemeData get militaryDark {
    return ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: MilitaryColors.background,
      primaryColor: MilitaryColors.primary,
      colorScheme: const ColorScheme.dark(
        primary: MilitaryColors.primary,
        secondary: MilitaryColors.info,
        error: MilitaryColors.error,
        surface: MilitaryColors.surface,
      ),
      textTheme: GoogleFonts.jetBrainsMonoTextTheme(
        const TextTheme(
          displayLarge: TextStyle(color: MilitaryColors.textPrimary, fontSize: 28, fontWeight: FontWeight.w700),
          displayMedium: TextStyle(color: MilitaryColors.textPrimary, fontSize: 24, fontWeight: FontWeight.w600),
          bodyLarge: TextStyle(color: MilitaryColors.textPrimary, fontSize: 16),
          bodyMedium: TextStyle(color: MilitaryColors.textSecondary, fontSize: 14),
          bodySmall: TextStyle(color: MilitaryColors.textMuted, fontSize: 12),
          labelLarge: TextStyle(color: MilitaryColors.textPrimary, fontSize: 14, fontWeight: FontWeight.w600),
        ),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: MilitaryColors.surface,
        foregroundColor: MilitaryColors.textPrimary,
        elevation: 0,
        centerTitle: true,
      ),
      cardTheme: CardTheme(
        color: MilitaryColors.surface,
        elevation: 2,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
          side: const BorderSide(color: MilitaryColors.surfaceLight, width: 0.5),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: MilitaryColors.primary,
          foregroundColor: MilitaryColors.background,
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
          textStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: MilitaryColors.surfaceLight,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(6),
          borderSide: const BorderSide(color: MilitaryColors.textMuted),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(6),
          borderSide: const BorderSide(color: MilitaryColors.textMuted),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(6),
          borderSide: const BorderSide(color: MilitaryColors.primary, width: 1.5),
        ),
        labelStyle: const TextStyle(color: MilitaryColors.textSecondary),
        hintStyle: const TextStyle(color: MilitaryColors.textMuted),
      ),
      dividerTheme: const DividerThemeData(
        color: MilitaryColors.surfaceLight,
        thickness: 0.5,
      ),
      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor: MilitaryColors.surface,
        selectedItemColor: MilitaryColors.primary,
        unselectedItemColor: MilitaryColors.textMuted,
      ),
    );
  }
}
