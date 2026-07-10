import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../../models/gate3_interaction_state.dart';

/// Animated circular frequency field around the Sedi brain orb.
class SediFrequencyRingPainter extends CustomPainter {
  final double phase;
  final double amplitude;
  final double glowOpacity;
  final Gate3InteractionState state;

  static const _barCount = 72;
  static const _oliveStroke = Color(0xFFB8C88A);
  static const _creamGlow = Color(0xFFE8E4C8);

  const SediFrequencyRingPainter({
    required this.phase,
    required this.amplitude,
    required this.glowOpacity,
    required this.state,
  });

  static double targetAmplitude(Gate3InteractionState state) {
    switch (state) {
      case Gate3InteractionState.idle:
        return 0.14;
      case Gate3InteractionState.listening:
        return 0.22;
      case Gate3InteractionState.thinking:
        return 0.38;
      case Gate3InteractionState.speaking:
        return 0.34;
    }
  }

  static double targetGlow(Gate3InteractionState state) {
    switch (state) {
      case Gate3InteractionState.idle:
        return 0.18;
      case Gate3InteractionState.listening:
        return 0.28;
      case Gate3InteractionState.thinking:
        return 0.42;
      case Gate3InteractionState.speaking:
        return 0.38;
    }
  }

  static double phaseSpeed(Gate3InteractionState state) {
    switch (state) {
      case Gate3InteractionState.idle:
        return 1.0;
      case Gate3InteractionState.listening:
        return 1.45;
      case Gate3InteractionState.thinking:
        return 2.1;
      case Gate3InteractionState.speaking:
        return 1.9;
    }
  }

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final outerRadius = size.width / 2;
    final baseRadius = outerRadius * 0.88;
    final animatedPhase = phase * phaseSpeed(state);

    // Soft outer glow halo
    final glowPaint = Paint()
      ..shader = ui.Gradient.radial(
        center,
        outerRadius,
        [
          _creamGlow.withOpacity(glowOpacity * 0.35),
          _creamGlow.withOpacity(0),
        ],
      );
    canvas.drawCircle(center, outerRadius * 0.98, glowPaint);

    final barPaint = Paint()
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    for (var i = 0; i < _barCount; i++) {
      final angle = (i / _barCount) * math.pi * 2 + animatedPhase * math.pi * 2;

      // Layered wave frequencies for organic motion
      final waveA = math.sin(angle * 5 + animatedPhase * math.pi * 8);
      final waveB = math.sin(angle * 11 - animatedPhase * math.pi * 6) * 0.55;
      final waveC = math.sin(angle * 3 + animatedPhase * math.pi * 4) * 0.35;
      final combined = (waveA + waveB + waveC) / 2.0;

      final normalized = (combined + 1) / 2;
      final barLength = baseRadius * amplitude * (0.35 + normalized * 0.95);
      final inner = center +
          Offset(math.cos(angle) * baseRadius, math.sin(angle) * baseRadius);
      final outer = center +
          Offset(
            math.cos(angle) * (baseRadius + barLength),
            math.sin(angle) * (baseRadius + barLength),
          );

      final opacity = 0.18 + normalized * 0.55;
      barPaint
        ..color = _oliveStroke.withOpacity(opacity * glowOpacity.clamp(0.2, 1.0))
        ..strokeWidth = 1.4 + normalized * 0.8;
      canvas.drawLine(inner, outer, barPaint);
    }

    // Thin luminous ring trace
    final ringPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2
      ..color = _oliveStroke.withOpacity(0.22 + glowOpacity * 0.3);
    canvas.drawCircle(center, baseRadius, ringPaint);
  }

  @override
  bool shouldRepaint(covariant SediFrequencyRingPainter oldDelegate) =>
      oldDelegate.phase != phase ||
      oldDelegate.amplitude != amplitude ||
      oldDelegate.glowOpacity != glowOpacity ||
      oldDelegate.state != state;
}
