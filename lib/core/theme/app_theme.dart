import 'package:flutter/material.dart';

/// ============================================
/// AppTheme - هویت بصری صدی
/// ============================================
///
/// RESPONSIBILITY:
/// - فقط رنگ‌ها، radius، shadow
/// - بدون UI widget
/// - بدون logic
/// ============================================
class AppTheme {
  AppTheme._(); // جلوگیری از ساخت instance

  // ===============================
  // Brand Colors (Sedi Identity)
  // ===============================

  /// سبز پسته‌ای – هویت اصلی صدی
  static const Color pistachioGreen = Color(0xFF8BC34A);

  /// خاکستری متال – حالت‌های خنثی و inactive
  static const Color metalGrey = Color(0xFF9E9E9E);

  /// مشکی – متن و آیکن فعال
  static const Color primaryBlack = Color(0xFF111111);

  /// سفید – بک‌گراند اصلی
  static const Color backgroundWhite = Color(0xFFFFFFFF);
  static const Color dangerRed = Color(0xFFD32F2F);

  // ===============================
  // Semantic Colors
  // ===============================
  static const Color primary = primaryBlack;
  static const Color background = backgroundWhite;
  static const Color surface = backgroundWhite;

  static const Color textPrimary = primaryBlack;
  static const Color textSecondary = metalGrey;

  static const Color iconInactive = metalGrey;
  static const Color iconActive = primaryBlack;

  static const Color borderInactive = metalGrey;
  static const Color borderActive = primaryBlack;

  /// Gate 2 — light gray input fill
  static const Color inputFillLight = Color(0xFFF3F3F3);

  /// Gate 2 — very light placeholder text
  static const Color placeholderLight = Color(0xFFBDBDBD);

  /// Gate 2 — selected language button fill
  static const Color languageSelectedFill = Color(0xFFE8E8E8);

  /// Gate 2 — disabled action button
  static const Color buttonDisabled = Color(0xFFD6D6D6);

  // ===============================
  // Gate 2 Luxury Palette
  // ===============================
  static const Color gate2WarmBackground = Color(0xFFFAFAF8);
  static const Color gate2CardWhite = Color(0xFFFFFFFF);
  static const Color gate2InputFill = Color(0xFFF4F4F2);
  static const Color gate2ButtonActive = Color(0xFF050505);
  /// Gate 2 primary CTA — calm olive green (not bright green).
  static const Color gate2ButtonOlive = Color(0xFF6F7F3A);
  static const Color gate2ButtonDisabled = Color(0xFFE3E3E0);
  static const Color gate2TextDisabled = Color(0xFF8A8A86);
  static const Color gate2Placeholder = Color(0xFFC8C8C4);
  static const Color gate2TextPrimary = Color(0xFF080808);
  static const Color gate2TextMuted = Color(0xFF8A8A86);
  static const Color gate2BorderSubtle = Color(0xFFD8D8D4);

  static const double gate2RadiusCard = 22;
  static const double gate2RadiusInput = 14;

  // ===============================
  // Gate 3 Premium Palette
  // ===============================
  /// Gate 3 — soft pale olive-green background (premium, calm; avoid pure white).
  static const Color gate3PaleOliveBackground = Color(0xFFF3F5EE);

  static const List<BoxShadow> gate2CardShadow = [
    BoxShadow(
      color: Color(0x0F000000),
      blurRadius: 24,
      offset: Offset(0, 8),
    ),
    BoxShadow(
      color: Color(0x08000000),
      blurRadius: 6,
      offset: Offset(0, 2),
    ),
  ];

  // ===============================
  // Radius
  // ===============================

  static const double radiusSmall = 8;
  static const double radiusMedium = 14;
  static const double radiusLarge = 18;

  // ===============================
  // Shadows (مینیمال)
  // ===============================

  static const List<BoxShadow> softShadow = [
    BoxShadow(
      color: Color(0x1A000000), // مشکی با opacity کم
      blurRadius: 8,
      offset: Offset(0, 2),
    ),
  ];

  // ===============================
  // Typography
  // ===============================
  static const TextStyle titleLarge = TextStyle(
    color: textPrimary,
    fontSize: 20,
    fontWeight: FontWeight.w700,
  );

  static const TextStyle titleMedium = TextStyle(
    color: textPrimary,
    fontSize: 16,
    fontWeight: FontWeight.w600,
  );

  static const TextStyle bodyPrimary = TextStyle(
    color: textPrimary,
    fontSize: 14,
  );

  static const TextStyle bodySecondary = TextStyle(
    color: textSecondary,
    fontSize: 14,
  );

  static const TextStyle caption = TextStyle(
    color: textSecondary,
    fontSize: 12,
  );
}
