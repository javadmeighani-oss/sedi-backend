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
  static const _horizontalSamples = 72;

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
        return 0.04;
      case Gate3InteractionState.listening:
        return 0.07;
      case Gate3InteractionState.thinking:
        return 0.32;
      case Gate3InteractionState.speaking:
        return 0.88;
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

  /// Derives decoupled phases from one animation controller value `[0, 1]`.
  static ({double circular, double horizontal}) derivePhases({
    required double controllerValue,
    required Gate3InteractionState state,
  }) {
    return (
      circular: controllerValue * circularPhaseSpeed(state),
      horizontal: controllerValue * horizontalPhaseSpeed(state),
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
    final peakHeight = 2.5 + horizontalEnergy * 18;

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
    final baselinePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 0.75
      ..color = _oliveStroke.withOpacity(
        (0.12 + horizontalEnergy * 0.2).clamp(0.08, 0.5),
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
            time: horizontalPhase,
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

      if (amp > 1.0) {
        peakPaint.color = _oliveStroke.withOpacity(
          (0.2 + (amp / peakHeight) * 0.55).clamp(0.14, 0.78),
        );
        canvas.drawLine(
          Offset(x, baselineY),
          Offset(x, baselineY - amp),
          peakPaint,
        );
        final lowerSpike = amp * (0.18 + ProceduralVoiceWaveform.asymmetricLowerFactor(
              normalizedX: t,
              isRightSide: isRightSide,
            ));
        canvas.drawLine(
          Offset(x, baselineY),
          Offset(x, baselineY + lowerSpike),
          peakPaint,
        );
      }
    }

    canvas.drawPath(baselinePath, baselinePaint);
    peakPaint
      ..strokeWidth = 0.95
      ..color = _oliveStroke.withOpacity(
        (0.16 + horizontalEnergy * 0.32).clamp(0.1, 0.72),
      );
    canvas.drawPath(peakPath, peakPaint);
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
