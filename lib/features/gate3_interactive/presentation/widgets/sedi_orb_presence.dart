import 'package:flutter/material.dart';

import '../../models/gate3_interaction_state.dart';
import 'sedi_brain_orb.dart';
import 'sedi_horizontal_resonance_visualizer.dart';

/// Full-width orb + horizontal resonance as one centered presence unit.
///
/// Layout: bars —— gap —— [protected Sedi orb] —— gap —— bars
/// Left/right segments share one phase clock and the same interaction state.
/// No bars are drawn behind/inside the orb.
class SediOrbPresence extends StatefulWidget {
  final Gate3InteractionState state;
  final String lang;

  /// Breathing gap between each resonance segment and the orb edge.
  static const double orbBreathingGap = 10;

  /// Horizontal inset from the A3 usable edge (responsive, not device-fixed).
  static const double horizontalInset = 12;

  static const int _barsPerSide = 14;
  static const int _globalBarTotal = _barsPerSide * 2;

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
            .clamp(SediBrainOrb.size, maxW)
            .toDouble();

        return SizedBox(
          width: usable,
          height: SediBrainOrb.size,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Expanded(
                child: SediHorizontalResonanceVisualizer(
                  state: widget.state,
                  phaseListenable: _phase,
                  segmentBarCount: SediOrbPresence._barsPerSide,
                  globalBarOffset: 0,
                  globalBarTotal: SediOrbPresence._globalBarTotal,
                ),
              ),
              const SizedBox(width: SediOrbPresence.orbBreathingGap),
              SediBrainOrb(state: widget.state, lang: widget.lang),
              const SizedBox(width: SediOrbPresence.orbBreathingGap),
              Expanded(
                child: SediHorizontalResonanceVisualizer(
                  state: widget.state,
                  phaseListenable: _phase,
                  segmentBarCount: SediOrbPresence._barsPerSide,
                  globalBarOffset: SediOrbPresence._barsPerSide,
                  globalBarTotal: SediOrbPresence._globalBarTotal,
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
