import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../../logic/procedural_voice_waveform.dart';
import '../../models/gate3_interaction_state.dart';
import 'sedi_audio_visualizer_geometry.dart';

/// Fine radial spectrum and horizontal voice waveform around the Sedi orb.
class SediAudioVisualizerPainter extends CustomPainter {
  final double circularPhase;
  final double horizontalPhase;
  final double horizontalEnergy;
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
  static const _horizontalSamples = 128;

  /// Fixed circular amplitude — identical in every interaction state.
  static double targetAmplitude(Gate3InteractionState state) =>
      SediCircularEqualizerProfile.amplitude;

  /// Fixed circular glow — identical in every interaction state.
  static double targetGlow(Gate3InteractionState state) =>
      SediCircularEqualizerProfile.glow;

  /// Constant circular rotation speed — identical in every interaction state.
  static double circularPhaseSpeed(Gate3InteractionState state) =>
      SediCircularEqualizerProfile.phaseSpeed;

  /// Horizontal resonance targets: idle ≈ listening < thinking << speaking.
  static double targetHorizontalEnergy(Gate3InteractionState state) {
    switch (state) {
      case Gate3InteractionState.idle:
        return 0.20;
      case Gate3InteractionState.listening:
        return 0.30;
      case Gate3InteractionState.thinking:
        return 0.58;
      case Gate3InteractionState.speaking:
        return 0.92;
    }
  }

  /// State-responsive horizontal cadence (circular cadence stays constant).
  static double horizontalPhaseSpeed(Gate3InteractionState state) {
    switch (state) {
      case Gate3InteractionState.idle:
        return 0.45;
      case Gate3InteractionState.listening:
        return 0.5;
      case Gate3InteractionState.thinking:
        return 0.95;
      case Gate3InteractionState.speaking:
        return 1.75;
    }
  }

  /// Constant circular phase from one animation controller value `[0, 1]`.
  static double deriveCircularPhase(double controllerValue) =>
      controllerValue * SediCircularEqualizerProfile.phaseSpeed;

  /// Integrates horizontal phase with smoothly interpolated speed.
  ///
  /// Speed is lerped toward the state target before each delta step so phase
  /// never jumps when [state] changes.
  static ({
    double phase,
    double speed,
    double lastControllerValue,
  }) advanceHorizontalPhase({
    required double phase,
    required double speed,
    required double lastControllerValue,
    required double controllerValue,
    required Gate3InteractionState state,
    double speedLerp = 0.12,
  }) {
    var delta = controllerValue - lastControllerValue;
    if (delta < 0) {
      delta += 1.0;
    }

    final targetSpeed = horizontalPhaseSpeed(state);
    final nextSpeed = speed + (targetSpeed - speed) * speedLerp;
    final nextPhase = phase + delta * nextSpeed;

    return (
      phase: nextPhase,
      speed: nextSpeed,
      lastControllerValue: controllerValue,
    );
  }

  const SediAudioVisualizerPainter({
    required this.circularPhase,
    required this.horizontalPhase,
    required this.horizontalEnergy,
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

  /// Computes spectrum radius and bar scaling that stay inside layout bounds.
  static SediVisualizerLayout resolveLayout({
    required double width,
    required double containerHeight,
    required double orbBodyRadius,
    double amplitude = SediCircularEqualizerProfile.amplitude,
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
    final circularAmplitude = SediCircularEqualizerProfile.amplitude;
    final circularGlow = SediCircularEqualizerProfile.glow;

    _paintGlow(canvas, size, circularAmplitude, circularGlow);
    _paintHorizontalWaveform(canvas, size);
    _paintRadialSpectrum(canvas, circularAmplitude, circularGlow);
  }

  void _paintGlow(
    Canvas canvas,
    Size size,
    double circularAmplitude,
    double circularGlow,
  ) {
    final barOutward = SediAudioVisualizerGeometry.radialBarOutwardExtent(
      circularAmplitude,
      barExtensionFactor: barExtensionFactor,
    );
    final shaderRadius =
        spectrumRadius + barOutward + glowShaderExtraBeyondBarExtension;
    final glowPaint = Paint()
      ..shader = ui.Gradient.radial(
        orbCenter,
        shaderRadius,
        [
          _creamGlow.withOpacity(circularGlow * 0.28),
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

  void _paintRadialSpectrum(
    Canvas canvas,
    double circularAmplitude,
    double circularGlow,
  ) {
    final baselinePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 0.9
      ..color = _oliveStroke.withOpacity(0.24 + circularGlow * 0.12);
    canvas.drawCircle(orbCenter, spectrumRadius, baselinePaint);

    final minBar = SediAudioVisualizerGeometry.minBarLength(
      circularAmplitude,
      barExtensionFactor: barExtensionFactor,
    );
    final maxBar = SediAudioVisualizerGeometry.maxBarLength(
      circularAmplitude,
      barExtensionFactor: barExtensionFactor,
    );

    final barPaint = Paint()
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    for (var i = 0; i < _barCount; i++) {
      final angle = (i / _barCount) * math.pi * 2;
      final energy = ProceduralVoiceWaveform.radialBarEnergy(
        angle: angle,
        time: circularPhase,
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

      final opacity = (0.16 + energy * 0.52) * (0.7 + circularGlow * 0.3);
      barPaint
        ..color = _oliveStroke.withOpacity(opacity.clamp(0.12, 0.82))
        ..strokeWidth = 0.55 + energy * 0.45;
      canvas.drawLine(inner, outer, barPaint);
    }
  }

  void _paintHorizontalWaveform(Canvas canvas, Size size) {
    final tangentX = spectrumRadius;
    final leftStart = orbCenter.dx - tangentX;
    final rightStart = orbCenter.dx + tangentX;
    final leftSpan = math.max(leftStart, 1.0);
    final rightSpan = math.max(size.width - rightStart, 1.0);
    final peakHeight = 3.0 + horizontalEnergy * 16;

    _paintHorizontalSide(
      canvas: canvas,
      startX: leftStart,
      endX: 0,
      span: leftSpan,
      peakHeight: peakHeight,
      isRightSide: false,
    );
    _paintHorizontalSide(
      canvas: canvas,
      startX: rightStart,
      endX: size.width,
      span: rightSpan,
      peakHeight: peakHeight,
      isRightSide: true,
    );
  }

  void _paintHorizontalSide({
    required Canvas canvas,
    required double startX,
    required double endX,
    required double span,
    required double peakHeight,
    required bool isRightSide,
  }) {
    if (span <= 6) return;

    final baselineY = orbCenter.dy;
    final upperPath = Path();
    final lowerPath = Path();
    final baselinePath = Path();

    final strokePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..strokeWidth = 0.8
      ..color = _oliveStroke.withOpacity(
        (0.14 + horizontalEnergy * 0.28).clamp(0.1, 0.62),
      );

    final fillPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..strokeWidth = 0.72
      ..color = _oliveStroke.withOpacity(
        (0.16 + horizontalEnergy * 0.34).clamp(0.12, 0.72),
      );

    for (var i = 0; i <= _horizontalSamples; i++) {
      final t = i / _horizontalSamples;
      final x = ui.lerpDouble(startX, endX, t)!;
      final sample = ProceduralVoiceWaveform.horizontalWaveformSample(
        normalizedX: t,
        time: horizontalPhase,
        energy: horizontalEnergy,
        state: state,
        isRightSide: isRightSide,
      );
      final upperY = baselineY - sample.upper * peakHeight;
      final lowerY = baselineY + sample.lower * peakHeight;

      if (i == 0) {
        baselinePath.moveTo(x, baselineY);
        upperPath.moveTo(x, upperY);
        lowerPath.moveTo(x, lowerY);
      } else {
        baselinePath.lineTo(x, baselineY);
        upperPath.lineTo(x, upperY);
        lowerPath.lineTo(x, lowerY);
      }
    }

    canvas.drawPath(baselinePath, strokePaint);
    canvas.drawPath(upperPath, fillPaint);
    canvas.drawPath(
      lowerPath,
      fillPaint
        ..strokeWidth = 0.66
        ..color = _oliveStroke.withOpacity(
          (0.12 + horizontalEnergy * 0.26).clamp(0.1, 0.58),
        ),
    );
  }

  @override
  bool shouldRepaint(covariant SediAudioVisualizerPainter oldDelegate) =>
      oldDelegate.circularPhase != circularPhase ||
      oldDelegate.horizontalPhase != horizontalPhase ||
      oldDelegate.horizontalEnergy != horizontalEnergy ||
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
