import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../../logic/procedural_voice_waveform.dart';
import '../../models/gate3_interaction_state.dart';
import 'sedi_audio_visualizer_geometry.dart';

/// Fine radial spectrum and horizontal bar equalizer around the Sedi orb.
class SediAudioVisualizerPainter extends CustomPainter {
  final double circularPhase;
  final double horizontalPhase;
  final double horizontalEnergy;
  final double horizontalDensity;
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

  /// Fixed circular amplitude — identical in every interaction state.
  static double targetAmplitude(Gate3InteractionState state) =>
      SediCircularEqualizerProfile.amplitude;

  /// Fixed circular glow — identical in every interaction state.
  static double targetGlow(Gate3InteractionState state) =>
      SediCircularEqualizerProfile.glow;

  /// Constant circular rotation speed — identical in every interaction state.
  static double circularPhaseSpeed(Gate3InteractionState state) =>
      SediCircularEqualizerProfile.phaseSpeed;

  /// Horizontal resonance amplitude targets relative to speaking (= 1.00).
  static double targetHorizontalEnergy(Gate3InteractionState state) =>
      SediHorizontalResonanceProfile.amplitudeTarget(state);

  /// Horizontal spatial-density targets relative to speaking (= 1.00).
  static double targetHorizontalDensity(Gate3InteractionState state) =>
      SediHorizontalResonanceProfile.densityTarget(state);

  /// Shared horizontal cadence — identical for every active state.
  static double horizontalPhaseSpeed(Gate3InteractionState state) =>
      1.0 / SediHorizontalResonanceProfile.cycleDurationSeconds;

  /// Constant circular phase from one animation controller value `[0, 1]`.
  static double deriveCircularPhase(double controllerValue) =>
      controllerValue * SediCircularEqualizerProfile.phaseSpeed;

  /// Integrates horizontal phase from elapsed real time in seconds.
  static double advanceHorizontalPhase({
    required double phase,
    required double dtSeconds,
  }) =>
      SediHorizontalResonanceProfile.advancePhase(phase, dtSeconds);

  const SediAudioVisualizerPainter({
    required this.circularPhase,
    required this.horizontalPhase,
    required this.horizontalEnergy,
    required this.horizontalDensity,
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
    _paintHorizontalEqualizer(canvas, size);
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

  void _paintHorizontalEqualizer(Canvas canvas, Size size) {
    final tangentX = spectrumRadius;
    final leftStart = orbCenter.dx - tangentX;
    final rightStart = orbCenter.dx + tangentX;
    final leftSpan = math.max(leftStart, 1.0);
    final rightSpan = math.max(size.width - rightStart, 1.0);
    final peakHeight = SediAudioVisualizerGeometry.clampHorizontalPeakHeight(
      3.0 + horizontalEnergy * 16,
    );
    final maxHalfHeight = SediAudioVisualizerGeometry.horizontalBarHalfHeightBudget();

    _paintHorizontalSide(
      canvas: canvas,
      startX: leftStart,
      endX: 0,
      span: leftSpan,
      peakHeight: peakHeight,
      maxHalfHeight: maxHalfHeight,
      isRightSide: false,
    );
    _paintHorizontalSide(
      canvas: canvas,
      startX: rightStart,
      endX: size.width,
      span: rightSpan,
      peakHeight: peakHeight,
      maxHalfHeight: maxHalfHeight,
      isRightSide: true,
    );
  }

  void _paintHorizontalSide({
    required Canvas canvas,
    required double startX,
    required double endX,
    required double span,
    required double peakHeight,
    required double maxHalfHeight,
    required bool isRightSide,
  }) {
    if (span <= SediHorizontalResonanceProfile.barPitch) return;

    final baselineY = orbCenter.dy;
    final barCount = SediHorizontalResonanceProfile.barCountForSpan(span);
    if (barCount <= 0) return;

    final pitch = span / barCount;
    final strokeWidth = SediHorizontalResonanceProfile.barStrokeWidth;
    final isIdle = horizontalEnergy <= 0.001 && horizontalDensity <= 0.001;

    final baselinePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..isAntiAlias = true
      ..strokeWidth = strokeWidth * 0.72
      ..color = _oliveStroke.withOpacity(
        SediHorizontalResonanceProfile.baselineOpacity,
      );

    canvas.drawLine(
      Offset(startX, baselineY),
      Offset(endX, baselineY),
      baselinePaint,
    );

    if (isIdle) return;

    final coreOpacity = _interpolatedBarOpacity();
    final barPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..isAntiAlias = true
      ..strokeWidth = strokeWidth
      ..color = _oliveStroke.withOpacity(coreOpacity);

    final glowPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..isAntiAlias = true
      ..strokeWidth = strokeWidth + 0.8
      ..color = _oliveStroke.withOpacity(
        SediHorizontalResonanceProfile.horizontalGlowOpacity * coreOpacity,
      );

    for (var i = 0; i < barCount; i++) {
      final t = (i + 0.5) / barCount;
      final x = ui.lerpDouble(startX, endX, t)!;
      final sample = ProceduralVoiceWaveform.horizontalWaveformSample(
        normalizedX: t,
        time: horizontalPhase,
        energy: horizontalEnergy,
        density: horizontalDensity,
        isRightSide: isRightSide,
      );

      if (sample.upper <= 0.0005 && sample.lower <= 0.0005) continue;

      final upperExtent = math.min(sample.upper * peakHeight, maxHalfHeight);
      final lowerExtent = math.min(sample.lower * peakHeight, maxHalfHeight);
      final upperY = baselineY - upperExtent;
      final lowerY = baselineY + lowerExtent;

      canvas.drawLine(Offset(x, baselineY), Offset(x, upperY), glowPaint);
      canvas.drawLine(Offset(x, baselineY), Offset(x, lowerY), glowPaint);
      canvas.drawLine(Offset(x, baselineY), Offset(x, upperY), barPaint);
      canvas.drawLine(Offset(x, baselineY), Offset(x, lowerY), barPaint);
    }
  }

  double _interpolatedBarOpacity() {
    final listening = SediHorizontalResonanceProfile.barCoreOpacity(
      Gate3InteractionState.listening,
    );
    final thinking = SediHorizontalResonanceProfile.barCoreOpacity(
      Gate3InteractionState.thinking,
    );
    final speaking = SediHorizontalResonanceProfile.barCoreOpacity(
      Gate3InteractionState.speaking,
    );

    final energy = horizontalEnergy.clamp(0.0, 1.0);
    if (energy <= 0.001) {
      return SediHorizontalResonanceProfile.baselineOpacity;
    }
    if (energy <= 0.25) {
      return ui.lerpDouble(
            SediHorizontalResonanceProfile.baselineOpacity,
            listening,
            energy / 0.25,
          ) ??
          listening;
    }
    if (energy <= 0.52) {
      return ui.lerpDouble(
            listening,
            thinking,
            (energy - 0.25) / 0.27,
          ) ??
          thinking;
    }
    return ui.lerpDouble(
          thinking,
          speaking,
          (energy - 0.52) / 0.48,
        ) ??
        speaking;
  }

  @override
  bool shouldRepaint(covariant SediAudioVisualizerPainter oldDelegate) =>
      oldDelegate.circularPhase != circularPhase ||
      oldDelegate.horizontalPhase != horizontalPhase ||
      oldDelegate.horizontalEnergy != horizontalEnergy ||
      oldDelegate.horizontalDensity != horizontalDensity ||
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
