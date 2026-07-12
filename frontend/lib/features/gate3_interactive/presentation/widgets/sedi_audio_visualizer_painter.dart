import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../../logic/procedural_voice_waveform.dart';
import '../../models/gate3_interaction_state.dart';

/// Organic circular equalizer and horizontal waveform extensions around the orb.
class SediAudioVisualizerPainter extends CustomPainter {
  final double phase;
  final double amplitude;
  final double horizontalEnergy;
  final double glowOpacity;
  final Gate3InteractionState state;
  final Offset orbCenter;
  final double orbOuterRadius;

  static const _oliveStroke = Color(0xFF9AB06E);
  static const _creamGlow = Color(0xFFE8E4C8);
  static const _visibilityBoost = 1.35;
  static const _circleSamples = 160;
  static const _horizontalSamples = 48;

  const SediAudioVisualizerPainter({
    required this.phase,
    required this.amplitude,
    required this.horizontalEnergy,
    required this.glowOpacity,
    required this.state,
    required this.orbCenter,
    required this.orbOuterRadius,
  });

  static double targetAmplitude(Gate3InteractionState state) {
    switch (state) {
      case Gate3InteractionState.idle:
        return 0.12 * _visibilityBoost;
      case Gate3InteractionState.listening:
        return 0.2 * _visibilityBoost;
      case Gate3InteractionState.thinking:
        return 0.34 * _visibilityBoost;
      case Gate3InteractionState.speaking:
        return 0.3 * _visibilityBoost;
    }
  }

  static double targetHorizontalEnergy(Gate3InteractionState state) {
    switch (state) {
      case Gate3InteractionState.idle:
        return 0.08 * _visibilityBoost;
      case Gate3InteractionState.listening:
        return 0.16 * _visibilityBoost;
      case Gate3InteractionState.thinking:
        return 0.07 * _visibilityBoost;
      case Gate3InteractionState.speaking:
        return 0.42 * _visibilityBoost;
    }
  }

  static double targetGlow(Gate3InteractionState state) {
    switch (state) {
      case Gate3InteractionState.idle:
        return 0.18 * _visibilityBoost;
      case Gate3InteractionState.listening:
        return 0.26 * _visibilityBoost;
      case Gate3InteractionState.thinking:
        return 0.4 * _visibilityBoost;
      case Gate3InteractionState.speaking:
        return 0.36 * _visibilityBoost;
    }
  }

  static double phaseSpeed(Gate3InteractionState state) {
    switch (state) {
      case Gate3InteractionState.idle:
        return 1.0;
      case Gate3InteractionState.listening:
        return 1.4;
      case Gate3InteractionState.thinking:
        return 2.05;
      case Gate3InteractionState.speaking:
        return 1.85;
    }
  }

  @override
  void paint(Canvas canvas, Size size) {
    final animatedPhase = phase * phaseSpeed(state);
    final ringRadius = orbOuterRadius * 1.08;

    _paintGlow(canvas, size, animatedPhase);
    _paintHorizontalWaves(canvas, size, animatedPhase);
    _paintCircularEqualizer(canvas, ringRadius, animatedPhase);
  }

  void _paintGlow(Canvas canvas, Size size, double animatedPhase) {
    final glowPaint = Paint()
      ..shader = ui.Gradient.radial(
        orbCenter,
        math.max(size.width, size.height) * 0.42,
        [
          _creamGlow.withOpacity(glowOpacity * 0.42),
          _creamGlow.withOpacity(0),
        ],
      );
    canvas.drawCircle(orbCenter, orbOuterRadius * 1.18, glowPaint);
  }

  void _paintCircularEqualizer(
    Canvas canvas,
    double ringRadius,
    double animatedPhase,
  ) {
    final baselinePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.1 * _visibilityBoost
      ..color =
          _oliveStroke.withOpacity((0.2 + glowOpacity * 0.22) * _visibilityBoost);
    canvas.drawCircle(orbCenter, ringRadius, baselinePaint);

    final wavePath = Path();
    final time = animatedPhase * math.pi * 2;
    final waveExtent = ringRadius * amplitude * 0.22;

    for (var i = 0; i <= _circleSamples; i++) {
      final t = i / _circleSamples;
      final angle = t * math.pi * 2 + time * 0.35;
      final energy = ProceduralVoiceWaveform.circularWaveEnergy(
        angle: angle,
        time: animatedPhase,
        state: state,
      );
      final normalized = (energy + 1) / 2;
      final radius = ringRadius + waveExtent * (0.35 + normalized * 0.95);
      final point = orbCenter +
          Offset(math.cos(angle) * radius, math.sin(angle) * radius);

      if (i == 0) {
        wavePath.moveTo(point.dx, point.dy);
      } else {
        wavePath.lineTo(point.dx, point.dy);
      }
    }
    wavePath.close();

    final wavePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..strokeWidth = 1.6 * _visibilityBoost
      ..color =
          _oliveStroke.withOpacity((0.28 + amplitude * 0.55) * _visibilityBoost);
    canvas.drawPath(wavePath, wavePaint);
  }

  void _paintHorizontalWaves(
    Canvas canvas,
    Size size,
    double animatedPhase,
  ) {
    final attachX = orbOuterRadius * 1.04;
    final leftStart = orbCenter.dx - attachX;
    final rightStart = orbCenter.dx + attachX;
    final leftSpan = math.max(leftStart, 1.0);
    final rightSpan = math.max(size.width - rightStart, 1.0);
    final maxOffset = 5.5 + horizontalEnergy * 14;

    _paintHorizontalSide(
      canvas: canvas,
      startX: leftStart,
      endX: 0,
      span: leftSpan,
      animatedPhase: animatedPhase,
      maxOffset: maxOffset,
      isRightSide: false,
      opacityScale: 0.9,
    );
    _paintHorizontalSide(
      canvas: canvas,
      startX: rightStart,
      endX: size.width,
      span: rightSpan,
      animatedPhase: animatedPhase,
      maxOffset: maxOffset,
      isRightSide: true,
      opacityScale: 0.9,
    );
  }

  void _paintHorizontalSide({
    required Canvas canvas,
    required double startX,
    required double endX,
    required double span,
    required double animatedPhase,
    required double maxOffset,
    required bool isRightSide,
    required double opacityScale,
  }) {
    if (span <= 4) return;

    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;

    for (final lane in [0.0, 0.55]) {
      final path = Path();
      for (var i = 0; i <= _horizontalSamples; i++) {
        final t = i / _horizontalSamples;
        final x = ui.lerpDouble(startX, endX, t)!;
        final normalizedX = t;
        final fade = math.pow(1 - normalizedX, 1.65).toDouble();
        final offset = ProceduralVoiceWaveform.horizontalWaveOffset(
              normalizedX: normalizedX,
              time: animatedPhase,
              energy: horizontalEnergy,
              state: state,
              isRightSide: isRightSide,
            ) *
            maxOffset *
            fade;

        final y = orbCenter.dy + offset + lane;
        if (i == 0) {
          path.moveTo(x, y);
        } else {
          path.lineTo(x, y);
        }
      }

      final laneOpacity =
          (0.14 + horizontalEnergy * 0.55 - lane * 0.08).clamp(0.08, 0.82);
      paint
        ..strokeWidth = (1.1 - lane * 0.25) * _visibilityBoost
        ..color = _oliveStroke.withOpacity(
          laneOpacity * opacityScale * glowOpacity.clamp(0.25, 1.0),
        );
      canvas.drawPath(path, paint);
    }
  }

  @override
  bool shouldRepaint(covariant SediAudioVisualizerPainter oldDelegate) =>
      oldDelegate.phase != phase ||
      oldDelegate.amplitude != amplitude ||
      oldDelegate.horizontalEnergy != horizontalEnergy ||
      oldDelegate.glowOpacity != glowOpacity ||
      oldDelegate.state != state ||
      oldDelegate.orbCenter != orbCenter ||
      oldDelegate.orbOuterRadius != orbOuterRadius;
}
