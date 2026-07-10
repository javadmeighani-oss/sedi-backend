import 'package:flutter/material.dart';

import '../../../../core/utils/brand_name.dart';
import '../../models/gate3_interaction_state.dart';
import 'sedi_frequency_ring_painter.dart';
import 'sedi_orb_texture_painter.dart';

/// Living Sedi brain orb — cream/olive sphere with animated frequency ring.
class SediBrainOrb extends StatefulWidget {
  final Gate3InteractionState state;
  final String lang;

  static const double size = 136;

  const SediBrainOrb({
    super.key,
    required this.state,
    required this.lang,
  });

  @override
  State<SediBrainOrb> createState() => _SediBrainOrbState();
}

class _SediBrainOrbState extends State<SediBrainOrb>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  double _amplitude = SediFrequencyRingPainter.targetAmplitude(
    Gate3InteractionState.idle,
  );
  double _glow = SediFrequencyRingPainter.targetGlow(
    Gate3InteractionState.idle,
  );

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 10),
    )..addListener(_tickVisualState)
      ..repeat();
  }

  @override
  void didUpdateWidget(covariant SediBrainOrb oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.state != widget.state) {
      _tickVisualState();
    }
  }

  void _tickVisualState() {
    final targetAmp = SediFrequencyRingPainter.targetAmplitude(widget.state);
    final targetGlow = SediFrequencyRingPainter.targetGlow(widget.state);
    final nextAmp = _amplitude + (targetAmp - _amplitude) * 0.12;
    final nextGlow = _glow + (targetGlow - _glow) * 0.12;
    if ((nextAmp - _amplitude).abs() > 0.0005 ||
        (nextGlow - _glow).abs() > 0.0005) {
      setState(() {
        _amplitude = nextAmp;
        _glow = nextGlow;
      });
    }
  }

  @override
  void dispose() {
    _controller.removeListener(_tickVisualState);
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final orbDiameter = SediBrainOrb.size * 0.72;
    final brand = sediBrandName(widget.lang);
    final brandFontSize = orbDiameter * 0.34;

    return SizedBox(
      width: SediBrainOrb.size,
      height: SediBrainOrb.size,
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, child) {
          return CustomPaint(
            painter: SediFrequencyRingPainter(
              phase: _controller.value,
              amplitude: _amplitude,
              glowOpacity: _glow,
              state: widget.state,
            ),
            child: Center(child: child),
          );
        },
        child: Container(
          width: orbDiameter,
          height: orbDiameter,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: const RadialGradient(
              colors: [
                Color(0xFFFFFFFF),
                Color(0xFFF7F5EE),
                Color(0xFFEDEBE0),
              ],
              stops: [0.0, 0.55, 1.0],
            ),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFFD8DFC8).withOpacity(0.55),
                blurRadius: 20,
                spreadRadius: 1,
              ),
              BoxShadow(
                color: const Color(0xFF8A9A6B).withOpacity(0.12),
                blurRadius: 28,
                offset: const Offset(0, 6),
              ),
            ],
            border: Border.all(
              color: const Color(0xFFE6E9DC).withOpacity(0.9),
            ),
          ),
          child: Stack(
            alignment: Alignment.center,
            children: [
              ClipOval(
                child: CustomPaint(
                  size: Size(orbDiameter, orbDiameter),
                  painter: SediOrbTexturePainter(phase: _controller.value),
                ),
              ),
              Text(
                '$brand.',
                style: TextStyle(
                  fontSize: brandFontSize,
                  fontWeight: FontWeight.w800,
                  color: const Color(0xFF4F5E38),
                  letterSpacing: -0.6,
                  height: 1.0,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
