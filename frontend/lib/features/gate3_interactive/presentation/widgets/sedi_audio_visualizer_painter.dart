import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../../logic/procedural_voice_waveform.dart';
import '../../models/gate3_interaction_state.dart';
import 'sedi_audio_visualizer_geometry.dart';

/// Fine radial spectrum and horizontal voice waveform around the Sedi orb.
class SediAudioVisualizerPainter extends CustomPainter {
  final double phase;
  final double amplitude;
  final double horizontalEnergy;
  final double glowOpacity;
  final Gate3InteractionState state;
  final Offset orbCenter;
  final double orbBodyRadius;
  final double spectrumRadius;
  final double barExtensionFactor;
  final double glowPaintRadiusBeyondSpectrum;
  final double glowShaderExtraBeyondBarExtension;

  static const _oliveStroke = Color(0xFF9AB06E);
  static const _creamGlow = Color(0xFFE8E4C8);
  static const _barCount = 144;
  static const _horizontalSamples = 72;

  const SediAudioVisualizerPainter({
    required this.phase,
    required this.amplitude,
    required this.horizontalEnergy,
    required this.glowOpacity,
    required this.state,
    required this.orbCenter,
    required this.orbBodyRadius,
    required this.spectrumRadius,
    this.barExtensionFactor = 1,
    this.glowPaintRadiusBeyondSpectrum =
        SediAudioVisualizerGeometry.glowPaintRadiusBeyondSpectrum,
    this.glowShaderExtraBeyondBarExtension =
        SediAudioVisualizerGeometry.glowShaderExtraBeyondBarExtension,
  });

  static double targetAmplitude(Gate3InteractionState state) {
    switch (state) {
      case Gate3InteractionState.idle:
        return 0.55;
      case Gate3InteractionState.listening:
        return 0.78;
      case Gate3InteractionState.thinking:
        return 0.92;
      case Gate3InteractionState.speaking:
        return 0.68;
    }
  }

  static double targetHorizontalEnergy(Gate3InteractionState state) {
    switch (state) {
      case Gate3InteractionState.idle:
        return 0.14;
      case Gate3InteractionState.listening:
        return 0.42;
      case Gate3InteractionState.thinking:
        return 0.12;
      case Gate3InteractionState.speaking:
        return 0.88;
    }
  }

  static double targetGlow(Gate3InteractionState state) {
    switch (state) {
      case Gate3InteractionState.idle:
        return 0.16;
      case Gate3InteractionState.listening:
        return 0.24;
      case Gate3InteractionState.thinking:
        return 0.3;
      case Gate3InteractionState.speaking:
        return 0.22;
    }
  }

  static double phaseSpeed(Gate3InteractionState state) {
    switch (state) {
      case Gate3InteractionState.idle:
        return 0.85;
      case Gate3InteractionState.listening:
        return 1.15;
      case Gate3InteractionState.thinking:
        return 1.65;
      case Gate3InteractionState.speaking:
        return 1.05;
    }
  }

  /// Computes spectrum radius and bar scaling that stay inside layout bounds.
  static SediVisualizerLayout resolveLayout({
    required double width,
    required double containerHeight,
    required double orbBodyRadius,
    double amplitude = SediAudioVisualizerGeometry.peakAmplitude,
  }) {
    return SediAudioVisualizerGeometry.resolveLayout(
      width: width,
      containerHeight: containerHeight,
      orbBodyRadius: orbBodyRadius,
      amplitude: amplitude,
    );
  }

  /// Computes a stable spectrum radius that stays inside layout bounds.
  static double resolveSpectrumRadius({
    required double width,
    required double containerHeight,
    required double orbBodyRadius,
    double sideInset = SediAudioVisualizerGeometry.sideInset,
    double verticalInset = SediAudioVisualizerGeometry.verticalInset,
  }) {
    return resolveLayout(
      width: width,
      containerHeight: containerHeight,
      orbBodyRadius: orbBodyRadius,
    ).spectrumRadius;
  }

  @override
  void paint(Canvas canvas, Size size) {
    final animatedPhase = phase * phaseSpeed(state);

    _paintGlow(canvas, size);
    _paintHorizontalWaveform(canvas, size, animatedPhase);
    _paintRadialSpectrum(canvas, animatedPhase);
  }

  void _paintGlow(Canvas canvas, Size size) {
    final barOutward = SediAudioVisualizerGeometry.radialBarOutwardExtent(
      amplitude,
      barExtensionFactor: barExtensionFactor,
    );
    final shaderRadius = spectrumRadius + barOutward + glowShaderExtraBeyondBarExtension;
    final glowPaint = Paint()
      ..shader = ui.Gradient.radial(
        orbCenter,
        shaderRadius,
        [
          _creamGlow.withOpacity(glowOpacity * 0.28),
          _creamGlow.withOpacity(0),
        ],
      );
    if (glowPaintRadiusBeyondSpectrum > 0) {
      canvas.drawCircle(
        orbCenter,
        spectrumRadius + glowPaintRadiusBeyondSpectrum,
        glowPaint,
      );
    }
  }

  void _paintRadialSpectrum(Canvas canvas, double animatedPhase) {
    final baselinePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 0.9
      ..color = _oliveStroke.withOpacity(0.24 + glowOpacity * 0.12);
    canvas.drawCircle(orbCenter, spectrumRadius, baselinePaint);

    final minBar = SediAudioVisualizerGeometry.minBarLength(
      amplitude,
      barExtensionFactor: barExtensionFactor,
    );
    final maxBar = SediAudioVisualizerGeometry.maxBarLength(
      amplitude,
      barExtensionFactor: barExtensionFactor,
    );

    final barPaint = Paint()
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    for (var i = 0; i < _barCount; i++) {
      final angle = (i / _barCount) * math.pi * 2;
      final energy = ProceduralVoiceWaveform.radialBarEnergy(
        angle: angle,
        time: animatedPhase,
        state: state,
      );
      final barLength = minBar + energy * (maxBar - minBar);
      final inner = orbCenter +
          Offset(
            math.cos(angle) * spectrumRadius,
            math.sin(angle) * spectrumRadius,
          );
      final outer = orbCenter +
          Offset(
            math.cos(angle) * (spectrumRadius + barLength),
            math.sin(angle) * (spectrumRadius + barLength),
          );

      final opacity = (0.16 + energy * 0.52) * (0.7 + glowOpacity * 0.3);
      barPaint
        ..color = _oliveStroke.withOpacity(opacity.clamp(0.12, 0.82))
        ..strokeWidth = 0.55 + energy * 0.45;
      canvas.drawLine(inner, outer, barPaint);
    }
  }

  void _paintHorizontalWaveform(
    Canvas canvas,
    Size size,
    double animatedPhase,
  ) {
    final tangentX = spectrumRadius;
    final leftStart = orbCenter.dx - tangentX;
    final rightStart = orbCenter.dx + tangentX;
    final leftSpan = math.max(leftStart, 1.0);
    final rightSpan = math.max(size.width - rightStart, 1.0);
    final peakHeight = 3.5 + horizontalEnergy * 16;

    _paintHorizontalSide(
      canvas: canvas,
      startX: leftStart,
      endX: 0,
      span: leftSpan,
      animatedPhase: animatedPhase,
      peakHeight: peakHeight,
      isRightSide: false,
    );
    _paintHorizontalSide(
      canvas: canvas,
      startX: rightStart,
      endX: size.width,
      span: rightSpan,
      animatedPhase: animatedPhase,
      peakHeight: peakHeight,
      isRightSide: true,
    );
  }

  void _paintHorizontalSide({
    required Canvas canvas,
    required double startX,
    required double endX,
    required double span,
    required double animatedPhase,
    required double peakHeight,
    required bool isRightSide,
  }) {
    if (span <= 6) return;

    final baselineY = orbCenter.dy;
    final baselinePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 0.75
      ..color = _oliveStroke.withOpacity(
        (0.14 + horizontalEnergy * 0.22).clamp(0.1, 0.55),
      );

    final peakPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 0.85;

    final baselinePath = Path();
    final peakPath = Path();

    for (var i = 0; i <= _horizontalSamples; i++) {
      final t = i / _horizontalSamples;
      final x = ui.lerpDouble(startX, endX, t)!;
      final fade = math.pow(1 - t, 1.55).toDouble();
      final amp = ProceduralVoiceWaveform.horizontalPeakAmplitude(
            normalizedX: t,
            time: animatedPhase,
            energy: horizontalEnergy,
            state: state,
            isRightSide: isRightSide,
          ) *
          peakHeight *
          fade;

      if (i == 0) {
        baselinePath.moveTo(x, baselineY);
        peakPath.moveTo(x, baselineY - amp);
      } else {
        baselinePath.lineTo(x, baselineY);
        peakPath.lineTo(x, baselineY - amp);
      }

      if (amp > 1.2) {
        peakPaint.color = _oliveStroke.withOpacity(
          (0.2 + (amp / peakHeight) * 0.55).clamp(0.14, 0.78),
        );
        canvas.drawLine(
          Offset(x, baselineY),
          Offset(x, baselineY - amp),
          peakPaint,
        );
        canvas.drawLine(
          Offset(x, baselineY),
          Offset(x, baselineY + amp * 0.28),
          peakPaint,
        );
      }
    }

    canvas.drawPath(baselinePath, baselinePaint);
    peakPaint
      ..strokeWidth = 0.95
      ..color = _oliveStroke.withOpacity(
        (0.18 + horizontalEnergy * 0.35).clamp(0.12, 0.72),
      );
    canvas.drawPath(peakPath, peakPaint);
  }

  @override
  bool shouldRepaint(covariant SediAudioVisualizerPainter oldDelegate) =>
      oldDelegate.phase != phase ||
      oldDelegate.amplitude != amplitude ||
      oldDelegate.horizontalEnergy != horizontalEnergy ||
      oldDelegate.glowOpacity != glowOpacity ||
      oldDelegate.state != state ||
      oldDelegate.orbCenter != orbCenter ||
      oldDelegate.orbBodyRadius != orbBodyRadius ||
      oldDelegate.spectrumRadius != spectrumRadius ||
      oldDelegate.barExtensionFactor != barExtensionFactor ||
      oldDelegate.glowPaintRadiusBeyondSpectrum !=
          glowPaintRadiusBeyondSpectrum ||
      oldDelegate.glowShaderExtraBeyondBarExtension !=
          glowShaderExtraBeyondBarExtension;
}
