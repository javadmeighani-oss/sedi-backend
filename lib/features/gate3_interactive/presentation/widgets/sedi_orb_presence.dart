import 'package:flutter/material.dart';

import '../../models/gate3_interaction_state.dart';
import 'sedi_brain_orb.dart';
import 'sedi_horizontal_resonance_visualizer.dart';
import 'sedi_presence_tokens.dart';

/// Full-width horizontal resonance with a centered Sedi circle on the same line.
class SediOrbPresence extends StatefulWidget {
  final Gate3InteractionState state;
  final String lang;

  /// Horizontal inset from the A3 usable edge (responsive, not device-fixed).
  static const double horizontalInset = 12;

  const SediOrbPresence({
    super.key,
    required this.state,
    required this.lang,
  });

  @override
  State<SediOrbPresence> createState() => _SediOrbPresenceState();
}

class _SediOrbPresenceState extends State<SediOrbPresence>
    with SingleTickerProviderStateMixin {
  late final AnimationController _phase;

  @override
  void initState() {
    super.initState();
    _phase = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 10),
    )..repeat();
  }

  @override
  void dispose() {
    _phase.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final maxW = constraints.maxWidth.isFinite
            ? constraints.maxWidth
            : MediaQuery.sizeOf(context).width;
        final usable = (maxW - SediOrbPresence.horizontalInset * 2)
            .clamp(SediPresenceTokens.orbMinDiameter, maxW)
            .toDouble();
        final orbD = SediBrainOrb.diameterFor(usable);
        final bars = SediPresenceTokens.barCountFor(usable);
        final height = orbD < SediPresenceTokens.visualizerHeight
            ? SediPresenceTokens.visualizerHeight
            : orbD;

        return SizedBox(
          width: usable,
          height: height,
          child: Stack(
            alignment: Alignment.center,
            children: [
              SediHorizontalResonanceVisualizer(
                state: widget.state,
                phaseListenable: _phase,
                segmentBarCount: bars,
                globalBarOffset: 0,
                globalBarTotal: bars,
              ),
              SediBrainOrb(
                state: widget.state,
                lang: widget.lang,
                diameter: orbD,
              ),
            ],
          ),
        );
      },
    );
  }
}
