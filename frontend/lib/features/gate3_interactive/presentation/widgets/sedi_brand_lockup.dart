import 'package:flutter/material.dart';

/// Fixed Latin brand mark for the Gate 3 brain orb.
///
/// Renders the canonical `Sedi.` wordmark image from the official logo asset.
/// Never localized, mirrored, or reordered regardless of page direction.
class SediBrandLockup extends StatelessWidget {
  static const String label = 'Sedi.';

  /// Official transparent production wordmark (`Sedi.` with trailing period).
  static const String assetPath = 'assets/images/logo/sedi_logo_1024.png';

  final double height;

  const SediBrandLockup({
    super.key,
    required this.height,
  });

  @override
  Widget build(BuildContext context) {
    return Directionality(
      textDirection: TextDirection.ltr,
      child: Semantics(
        label: label,
        child: Image.asset(
          assetPath,
          height: height,
          fit: BoxFit.contain,
          filterQuality: FilterQuality.high,
          gaplessPlayback: true,
          matchTextDirection: false,
        ),
      ),
    );
  }
}
