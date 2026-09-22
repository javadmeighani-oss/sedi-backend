import 'package:flutter/material.dart';

import '../../models/gate3_interaction_state.dart';
import 'sedi_brain_orb.dart';
import 'sedi_horizontal_resonance_visualizer.dart';

/// Orb + horizontal resonance as one centered presence unit.
///
/// The resonance band shares the orb's vertical center. It stays inside the
/// orb column (not screen-width). The orb is painted above the band so the
/// fixed Latin brand stays readable.
class SediOrbPresence extends StatelessWidget {
  final Gate3InteractionState state;
  final String lang;

  /// Slightly wider than the orb so the centerline flanks the sphere
  /// without becoming a screen-width strip.
  static const double presenceWidth = SediBrainOrb.size * 1.12;

  const SediOrbPresence({
    super.key,
    required this.state,
    required this.lang,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: presenceWidth,
      height: SediBrainOrb.size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          SizedBox(
            width: presenceWidth,
            height: SediHorizontalResonanceVisualizer.height,
            child: SediHorizontalResonanceVisualizer(state: state),
          ),
          SediBrainOrb(state: state, lang: lang),
        ],
      ),
    );
  }
}
