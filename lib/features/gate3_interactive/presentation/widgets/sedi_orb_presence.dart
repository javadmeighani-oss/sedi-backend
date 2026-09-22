import 'package:flutter/material.dart';

import '../../models/gate3_interaction_state.dart';
import 'sedi_brain_orb.dart';
import 'sedi_horizontal_resonance_visualizer.dart';

/// Orb + horizontal resonance as one centered presence unit.
///
/// Resonance width is locked to the orb column so bars are not a full-bleed
/// strip detached below the circular identity.
class SediOrbPresence extends StatelessWidget {
  final Gate3InteractionState state;
  final String lang;

  /// Slightly wider than the orb so bars read as a base under the sphere.
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
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SediBrainOrb(state: state, lang: lang),
          SizedBox(
            width: presenceWidth,
            height: SediHorizontalResonanceVisualizer.height,
            child: SediHorizontalResonanceVisualizer(state: state),
          ),
        ],
      ),
    );
  }
}
