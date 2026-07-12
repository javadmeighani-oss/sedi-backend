import 'package:flutter/material.dart';

/// Fixed Latin brand mark for the Gate 3 brain orb.
///
/// Always renders exactly `Sedi.` with the period on the right, isolated from
/// inherited RTL/BiDi layout regardless of app locale or page direction.
class SediBrandLockup extends StatelessWidget {
  static const String label = 'Sedi.';

  final double fontSize;
  final Color color;
  final double letterSpacing;

  const SediBrandLockup({
    super.key,
    required this.fontSize,
    this.color = const Color(0xFF4F5E38),
    this.letterSpacing = -0.6,
  });

  @override
  Widget build(BuildContext context) {
    return Directionality(
      textDirection: TextDirection.ltr,
      child: Text(
        label,
        textDirection: TextDirection.ltr,
        textAlign: TextAlign.center,
        style: TextStyle(
          fontSize: fontSize,
          fontWeight: FontWeight.w800,
          color: color,
          letterSpacing: letterSpacing,
          height: 1.0,
        ),
      ),
    );
  }
}
