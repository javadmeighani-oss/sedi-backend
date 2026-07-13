import 'dart:math' as math;

import '../../models/gate3_interaction_state.dart';

/// Immutable circular equalizer profile — screenshot `11.jpg` / idle authority.
///
/// The circular spectrum uses this profile in every interaction state.
class SediCircularEqualizerProfile {
  SediCircularEqualizerProfile._();

  /// Steady radial bar envelope (formerly idle amplitude target).
  static const double amplitude = 0.55;

  /// Restrained halo opacity (formerly idle glow target).
  static const double glow = 0.16;

  /// Constant controller phase multiplier for circular rotation.
  static const double phaseSpeed = 0.85;

  /// Travelling-cluster motion speed inside [ProceduralVoiceWaveform].
  static const double radialMotionSpeed = 0.75;
}

/// State-dependent horizontal resonance targets for Gate 3.
///
/// Amplitude and spatial density vary by interaction state. Temporal animation
/// speed is fixed for every active state via [cycleDurationSeconds].
class SediHorizontalResonanceProfile {
  SediHorizontalResonanceProfile._();

  /// One full horizontal perceptual cycle in seconds.
  static const double cycleDurationSeconds = 2.6;

  /// Exponential smoothing time constant (~95% settle in ~325 ms).
  static const double transitionTauSeconds = 0.115;

  /// Horizontal bar pitch in logical pixels.
  static const double barPitch = 2.7;

  /// Maximum accepted visual delta per frame (~30 Hz).
  static const double maxVisualDeltaSeconds = 1 / 30;

  /// Gaps above this threshold are treated as pause/resume and discarded once.
  static const double resumeGapThresholdSeconds = 0.10;

  /// Horizontal bar stroke width in logical pixels.
  static const double barStrokeWidth = 1.4;

  /// Optional horizontal glow opacity cap.
  static const double horizontalGlowOpacity = 0.09;

  /// Effective peak-amplitude hierarchy relative to speaking (= 1.00).
  static double amplitudeTarget(Gate3InteractionState state) {
    switch (state) {
      case Gate3InteractionState.idle:
        return 0.0;
      case Gate3InteractionState.listening:
        return 0.25;
      case Gate3InteractionState.thinking:
        return 0.52;
      case Gate3InteractionState.speaking:
        return 1.0;
    }
  }

  /// Spatial cluster richness hierarchy relative to speaking (= 1.00).
  static double densityTarget(Gate3InteractionState state) {
    switch (state) {
      case Gate3InteractionState.idle:
        return 0.0;
      case Gate3InteractionState.listening:
        return 0.28;
      case Gate3InteractionState.thinking:
        return 0.60;
      case Gate3InteractionState.speaking:
        return 1.0;
    }
  }

  /// Bar-core opacity for the committed interaction state.
  static double barCoreOpacity(Gate3InteractionState state) {
    switch (state) {
      case Gate3InteractionState.idle:
        return 0.20;
      case Gate3InteractionState.listening:
        return 0.40;
      case Gate3InteractionState.thinking:
        return 0.48;
      case Gate3InteractionState.speaking:
        return 0.55;
    }
  }

  /// Idle baseline opacity.
  static const double baselineOpacity = 0.20;

  /// Frame-rate-independent exponential smoothing.
  static double smoothToward(
    double current,
    double target,
    double dtSeconds, {
    double tauSeconds = transitionTauSeconds,
  }) {
    if (!current.isFinite || !target.isFinite || !dtSeconds.isFinite) {
      return target.isFinite ? target : current;
    }
    if (dtSeconds <= 0) return current;
    final alpha = 1 - math.exp(-dtSeconds / tauSeconds);
    return current + (target - current) * alpha;
  }

  /// Advances horizontal phase in cycle units `[0, ∞)` from elapsed seconds.
  static double advancePhase(double phase, double dtSeconds) {
    if (!phase.isFinite || !dtSeconds.isFinite || dtSeconds <= 0) {
      return phase;
    }
    return phase + dtSeconds / cycleDurationSeconds;
  }

  /// Approximate bar count for a horizontal span.
  static int barCountForSpan(double span) {
    if (!span.isFinite || span <= barPitch) return 0;
    return (span / barPitch).floor().clamp(0, 160);
  }

  /// Sanitizes elapsed wall time into a safe visual delta for one tick.
  ///
  /// [lastElapsedSeconds] inside the result is always [elapsedSeconds] so a
  /// discarded resume gap is not re-applied on the next frame.
  static ({
    double safeDt,
    double lastElapsedSeconds,
  }) sanitizeVisualDelta({
    required double elapsedSeconds,
    required double lastElapsedSeconds,
  }) {
    final rawDt = elapsedSeconds - lastElapsedSeconds;
    final updatedLast = elapsedSeconds;

    if (!rawDt.isFinite || rawDt <= 0) {
      return (safeDt: 0.0, lastElapsedSeconds: updatedLast);
    }
    if (rawDt > resumeGapThresholdSeconds) {
      return (safeDt: 0.0, lastElapsedSeconds: updatedLast);
    }
    return (
      safeDt: math.min(rawDt, maxVisualDeltaSeconds),
      lastElapsedSeconds: updatedLast,
    );
  }

  /// Advances phase, energy and density using the same sanitized delta.
  static ({
    double phase,
    double energy,
    double density,
    double lastElapsedSeconds,
    double safeDt,
  }) advanceVisualState({
    required double phase,
    required double energy,
    required double density,
    required double elapsedSeconds,
    required double lastElapsedSeconds,
    required double energyTarget,
    required double densityTarget,
  }) {
    final sanitized = sanitizeVisualDelta(
      elapsedSeconds: elapsedSeconds,
      lastElapsedSeconds: lastElapsedSeconds,
    );
    final safeDt = sanitized.safeDt;

    return (
      phase: advancePhase(phase, safeDt),
      energy: smoothToward(energy, energyTarget, safeDt),
      density: smoothToward(density, densityTarget, safeDt),
      lastElapsedSeconds: sanitized.lastElapsedSeconds,
      safeDt: safeDt,
    );
  }
}

/// Authoritative layout geometry for the Gate 3 radial spectrum visualizer.
///
/// Layout resolution and [SediAudioVisualizerPainter] share the same resolved
/// bar extension, glow paint radius, and shader envelope values.
class SediAudioVisualizerGeometry {
  SediAudioVisualizerGeometry._();

  /// Approved 10% reduction from commit `628b310` normal non-keyboard size.
  static const double visualizerSizeScale = 0.90;

  static double get barExtensionScale => 14.0 * visualizerSizeScale;
  static double get barLengthFloor => 3.0 * visualizerSizeScale;
  static double get barLengthMinBase => 1.2 * visualizerSizeScale;
  static const double barLengthMinAmplitudeScale = 0.8;

  static double get maxBarStrokeWidth => 1.0 * visualizerSizeScale;
  static double get strokeSafetyMargin => maxBarStrokeWidth / 2;
  static double get antiAliasSafetyMargin => 0.5 * visualizerSizeScale;

  static const double glowPaintRadiusBeyondSpectrum = 6.0 * visualizerSizeScale;
  static const double glowShaderExtraBeyondBarExtension =
      4.0 * visualizerSizeScale;

  /// Fixed circular amplitude used for bar extent and containment (all states).
  static const double peakAmplitude = SediCircularEqualizerProfile.amplitude;

  /// Outward budget for preferred canvas height only.
  static double get preferredCanvasOutwardBudget => 20.88 * visualizerSizeScale;

  static double get preferredSpectrumOffset => 10.0 * visualizerSizeScale;
  static double get minSpectrumOffset => 7.0 * visualizerSizeScale;
  static double get maxSpectrumOffset => 18.0 * visualizerSizeScale;
  static double get degradedMinSpectrumOffset => 3.0 * visualizerSizeScale;

  static const double sideInset = 8.0 * visualizerSizeScale;
  static const double verticalInset = 6.0 * visualizerSizeScale;

  /// Vertical half-extent budget for horizontal bar tips from the baseline.
  static double horizontalBarHalfHeightBudget() {
    final horizontalStrokeInset =
        SediHorizontalResonanceProfile.barStrokeWidth / 2;
    return math.max(
      0,
      preferredCanvasOutwardBudget -
          antiAliasSafetyMargin -
          horizontalStrokeInset,
    );
  }

  /// Clamps requested peak height to the geometry-derived outward budget.
  static double clampHorizontalPeakHeight(double peakHeight) {
    if (!peakHeight.isFinite) return 0;
    return math.min(peakHeight, horizontalBarHalfHeightBudget());
  }

  /// Per-side and total horizontal bar counts for a canvas width.
  static ({
    int perSide,
    int total,
    double spanPerSide,
  }) horizontalBarCountsForCanvasWidth({
    required double width,
    required double containerHeight,
    required double orbBodyRadius,
  }) {
    final layout = resolveLayout(
      width: width,
      containerHeight: containerHeight,
      orbBodyRadius: orbBodyRadius,
    );
    final spanPerSide = math.max(width / 2 - layout.spectrumRadius, 1.0);
    final perSide = SediHorizontalResonanceProfile.barCountForSpan(spanPerSide);
    return (
      perSide: perSide,
      total: perSide * 2,
      spanPerSide: spanPerSide,
    );
  }

  static double maxBarLength(double amplitude, {double barExtensionFactor = 1}) {
    final factor = barExtensionFactor.clamp(0.0, 1.0);
    return barLengthFloor + amplitude * barExtensionScale * factor;
  }

  static double minBarLength(double amplitude, {double barExtensionFactor = 1}) {
    final factor = barExtensionFactor.clamp(0.0, 1.0);
    return barLengthMinBase + amplitude * barLengthMinAmplitudeScale * factor;
  }

  /// Radial bar + stroke envelope measured outward from the spectrum ring.
  static double radialBarOutwardExtent(
    double amplitude, {
    double barExtensionFactor = 1,
  }) {
    return maxBarLength(amplitude, barExtensionFactor: barExtensionFactor) +
        strokeSafetyMargin +
        antiAliasSafetyMargin;
  }

  /// Complete outward paint budget from [spectrumRadius], matching the painter.
  static double maximumPaintedOutwardExtent(
    double amplitude, {
    double barExtensionFactor = 1,
    double glowPaintRadius = glowPaintRadiusBeyondSpectrum,
    double glowShaderExtra = glowShaderExtraBeyondBarExtension,
  }) {
    final barOutward = radialBarOutwardExtent(
      amplitude,
      barExtensionFactor: barExtensionFactor,
    );
    return math.max(
      barOutward + glowShaderExtra,
      glowPaintRadius,
    );
  }

  static double maximumPaintedOutwardExtentAtPeak({
    double barExtensionFactor = 1,
    double glowPaintRadius = glowPaintRadiusBeyondSpectrum,
    double glowShaderExtra = glowShaderExtraBeyondBarExtension,
  }) {
    return maximumPaintedOutwardExtent(
      peakAmplitude,
      barExtensionFactor: barExtensionFactor,
      glowPaintRadius: glowPaintRadius,
      glowShaderExtra: glowShaderExtra,
    );
  }

  /// Geometry-derived preferred visualizer canvas height for the approved orb.
  static double preferredCanvasHeight(double orbBodyRadius) {
    final spectrumRadius = orbBodyRadius + preferredSpectrumOffset;
    return 2 * (verticalInset + spectrumRadius + preferredCanvasOutwardBudget);
  }

  /// Minimum canvas that keeps the orb outside the spectrum baseline.
  static double minimumCanvasHeight(double orbBodyRadius) {
    final spectrumRadius = orbBodyRadius + degradedMinSpectrumOffset;
    final outward = maximumPaintedOutwardExtent(
      peakAmplitude,
      barExtensionFactor: 0,
      glowPaintRadius: 0,
      glowShaderExtra: 0,
    );
    return 2 * (verticalInset + spectrumRadius + outward);
  }

  static double _safeClamp(double value, double lower, double upper) {
    if (!value.isFinite) return lower;
    if (lower > upper) return upper;
    return value.clamp(lower, upper);
  }

  static double _availableCanvasRadius({
    required double width,
    required double containerHeight,
  }) {
    final halfHeight = (containerHeight / 2) - verticalInset;
    final halfWidth = (width / 2) - sideInset;
    return math.max(0, math.min(halfHeight, halfWidth));
  }

  static bool _layoutFits({
    required double canvasRadius,
    required double spectrumRadius,
    required double amplitude,
    required double barExtensionFactor,
    required double glowPaintRadius,
    required double glowShaderExtra,
  }) {
    if (canvasRadius <= 0 || spectrumRadius <= 0) return false;
    final outward = maximumPaintedOutwardExtent(
      amplitude,
      barExtensionFactor: barExtensionFactor,
      glowPaintRadius: glowPaintRadius,
      glowShaderExtra: glowShaderExtra,
    );
    return spectrumRadius + outward <= canvasRadius + 1e-6;
  }

  static SediVisualizerLayout resolveLayout({
    required double width,
    required double containerHeight,
    required double orbBodyRadius,
    double amplitude = SediCircularEqualizerProfile.amplitude,
  }) {
    final canvasRadius = _availableCanvasRadius(
      width: width,
      containerHeight: containerHeight,
    );

    final minSpectrum = orbBodyRadius + degradedMinSpectrumOffset;
    final nominalMaxSpectrum = orbBodyRadius + maxSpectrumOffset;
    final preferredSpectrum = orbBodyRadius + preferredSpectrumOffset;

    var spectrumRadius = _safeClamp(
      preferredSpectrum,
      minSpectrum,
      nominalMaxSpectrum,
    );

    var barExtensionFactor = 1.0;
    var glowPaintRadius = glowPaintRadiusBeyondSpectrum;
    var glowShaderExtra = glowShaderExtraBeyondBarExtension;

    bool fits() => _layoutFits(
          canvasRadius: canvasRadius,
          spectrumRadius: spectrumRadius,
          amplitude: amplitude,
          barExtensionFactor: barExtensionFactor,
          glowPaintRadius: glowPaintRadius,
          glowShaderExtra: glowShaderExtra,
        );

    for (var pass = 0; pass < 240 && !fits(); pass++) {
      if (barExtensionFactor > 0) {
        barExtensionFactor = math.max(0, barExtensionFactor - 0.05);
        continue;
      }
      if (glowShaderExtra > 0) {
        glowShaderExtra = math.max(0, glowShaderExtra - 1);
        continue;
      }
      if (glowPaintRadius > 0) {
        glowPaintRadius = math.max(0, glowPaintRadius - 1);
        continue;
      }
      if (spectrumRadius > orbBodyRadius + 2) {
        spectrumRadius = math.max(orbBodyRadius + 2, spectrumRadius - 0.5);
        continue;
      }
      break;
    }

    final baselineOnly = maximumPaintedOutwardExtent(
      amplitude,
      barExtensionFactor: 0,
      glowPaintRadius: 0,
      glowShaderExtra: 0,
    );
    final maxSpectrumForCanvas = math.max(
      orbBodyRadius + 2,
      canvasRadius - baselineOnly,
    );
    spectrumRadius = _safeClamp(
      spectrumRadius,
      orbBodyRadius + 2,
      math.max(orbBodyRadius + 2, maxSpectrumForCanvas),
    );

    if (!_layoutFits(
      canvasRadius: canvasRadius,
      spectrumRadius: spectrumRadius,
      amplitude: amplitude,
      barExtensionFactor: barExtensionFactor,
      glowPaintRadius: glowPaintRadius,
      glowShaderExtra: glowShaderExtra,
    )) {
      final availableOutward = math.max(0, canvasRadius - spectrumRadius);
      final barBudget = availableOutward -
          glowPaintRadius -
          strokeSafetyMargin -
          antiAliasSafetyMargin -
          barLengthFloor;
      if (barBudget <= 0 || amplitude <= 0) {
        barExtensionFactor = 0;
      } else {
        barExtensionFactor = _safeClamp(
          barBudget / (amplitude * barExtensionScale),
          0,
          1,
        );
      }
      glowShaderExtra = 0;
      glowPaintRadius = math.min(
        glowPaintRadius,
        math.max(0, availableOutward - radialBarOutwardExtent(
              amplitude,
              barExtensionFactor: barExtensionFactor,
            )),
      );
    }

    spectrumRadius = _safeClamp(
      spectrumRadius,
      orbBodyRadius + 2,
      math.max(orbBodyRadius + 2, canvasRadius),
    );
    barExtensionFactor = barExtensionFactor.clamp(0.0, 1.0);
    glowPaintRadius = glowPaintRadius.clamp(0.0, glowPaintRadiusBeyondSpectrum);
    glowShaderExtra =
        glowShaderExtra.clamp(0.0, glowShaderExtraBeyondBarExtension);

    return SediVisualizerLayout(
      spectrumRadius: spectrumRadius,
      barExtensionFactor: barExtensionFactor,
      glowPaintRadiusBeyondSpectrum: glowPaintRadius,
      glowShaderExtraBeyondBarExtension: glowShaderExtra,
    );
  }

  /// Verifies the radial spectrum stays inside the visualizer canvas.
  static bool paintedExtentFits({
    required double width,
    required double containerHeight,
    required SediVisualizerLayout layout,
    required double amplitude,
  }) {
    if (width <= 0 || containerHeight <= 0) return false;
    if (!layout.spectrumRadius.isFinite || layout.spectrumRadius <= 0) {
      return false;
    }

    final canvasRadius = _availableCanvasRadius(
      width: width,
      containerHeight: containerHeight,
    );
    return _layoutFits(
      canvasRadius: canvasRadius,
      spectrumRadius: layout.spectrumRadius,
      amplitude: amplitude,
      barExtensionFactor: layout.barExtensionFactor,
      glowPaintRadius: layout.glowPaintRadiusBeyondSpectrum,
      glowShaderExtra: layout.glowShaderExtraBeyondBarExtension,
    );
  }
}

class SediVisualizerLayout {
  final double spectrumRadius;
  final double barExtensionFactor;
  final double glowPaintRadiusBeyondSpectrum;
  final double glowShaderExtraBeyondBarExtension;

  const SediVisualizerLayout({
    required this.spectrumRadius,
    required this.barExtensionFactor,
    required this.glowPaintRadiusBeyondSpectrum,
    required this.glowShaderExtraBeyondBarExtension,
  });
}
