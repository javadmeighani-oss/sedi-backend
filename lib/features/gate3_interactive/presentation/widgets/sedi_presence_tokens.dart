import 'package:flutter/material.dart';

/// A3 Sedi-presence visual tokens only. Not the destination design system.
class SediPresenceTokens {
  SediPresenceTokens._();

  /// Approved Sedi-presence green — outline, brand, and horizontal bars.
  static const Color presenceGreen = Color(0xFF86F83C);

  static const double orbWidthFactor = 0.255;
  static const double orbMinDiameter = 92;
  static const double orbMaxDiameter = 104;

  static const double visualizerHeight = 36;
  static const double barPitch = 4;
  static const int barCountMin = 96;
  static const int barCountMax = 100;

  /// ~20% reduction from the previous visual-amplitude maximum.
  static const double amplitudeScale = 0.80;

  static double orbDiameterFor(double availableWidth) {
    return (availableWidth * orbWidthFactor)
        .clamp(orbMinDiameter, orbMaxDiameter)
        .toDouble();
  }

  static int barCountFor(double availableWidth) {
    return (availableWidth / barPitch)
        .round()
        .clamp(barCountMin, barCountMax);
  }
}
