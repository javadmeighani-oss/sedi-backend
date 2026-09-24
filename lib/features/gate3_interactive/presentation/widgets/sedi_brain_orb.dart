import 'package:flutter/material.dart';

import '../../../../core/utils/brand_name.dart';
import '../../models/gate3_interaction_state.dart';
import 'sedi_presence_tokens.dart';

/// Reference-style Sedi presence circle — white fill, green outline, Latin brand.
class SediBrainOrb extends StatelessWidget {
  final Gate3InteractionState state;
  final String lang;
  final double? diameter;

  static const double widthFactor = SediPresenceTokens.orbWidthFactor;
  static const double minDiameter = SediPresenceTokens.orbMinDiameter;
  static const double maxDiameter = SediPresenceTokens.orbMaxDiameter;

  static double diameterFor(double availableWidth) =>
      SediPresenceTokens.orbDiameterFor(availableWidth);

  const SediBrainOrb({
    super.key,
    required this.state,
    required this.lang,
    this.diameter,
  });

  @override
  Widget build(BuildContext context) {
    final d = diameter ?? SediPresenceTokens.orbMinDiameter;
    final brandFontSize = d * 0.34;

    return SizedBox(
      width: d,
      height: d,
      child: DecoratedBox(
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: const Color(0xFFFFFFFF),
          border: Border.all(
            color: SediPresenceTokens.presenceGreen,
            width: 2.2,
          ),
        ),
        child: Center(
          child: Directionality(
            textDirection: TextDirection.ltr,
            child: Text(
              sediOrbBrandLatin,
              style: TextStyle(
                fontSize: brandFontSize,
                fontWeight: FontWeight.w800,
                color: SediPresenceTokens.presenceGreen,
                letterSpacing: -0.6,
                height: 1.0,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
