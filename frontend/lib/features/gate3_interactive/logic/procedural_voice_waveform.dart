import 'dart:math' as math;

import '../presentation/widgets/sedi_audio_visualizer_geometry.dart';

/// Deterministic procedural waveform energy for Gate 3 audio visualization.
///
/// Circular energy is state-independent. Horizontal resonance uses three
/// simultaneous layers (micro, medium, clustered peaks) and is **not**
/// synchronized to real TTS or playback amplitude.
class ProceduralVoiceWaveform {
  ProceduralVoiceWaveform._();

  static const int clusterCount = 7;
  static const double _flatEpsilon = 1e-6;
  static const double _clusterFeather = 0.09;

  /// Radial bar length factor in `[0, 1]` for the circular spectrum.
  static double radialBarEnergy({
    required double angle,
    required double time,
  }) {
    final speed = SediCircularEqualizerProfile.radialMotionSpeed;
    final t = time * speed * math.pi * 2;
    final travel = angle - t * 0.85;

    final clusterA = math.pow(math.sin(travel * 3.4 + 0.8), 2).toDouble();
    final clusterB =
        math.pow(math.sin(travel * 5.1 - t * 0.35 + 1.4), 2).toDouble() * 0.55;
    final clusterC =
        math.pow(math.sin(travel * 8.2 + t * 0.2), 2).toDouble() * 0.28;

    final energy = clusterA + clusterB + clusterC;
    final micro = (math.sin(angle * 28 + t * 4) + 1) * 0.035;

    return (energy * 0.42 + micro).clamp(0.0, 1.0);
  }

  /// Organic horizontal waveform sample with asymmetric upper/lower envelopes.
  ///
  /// [normalizedX] is 0 at the circle tangent and 1 at the screen edge.
  /// [density] is the continuously interpolated spatial-density value.
  static ({double upper, double lower}) horizontalWaveformSample({
    required double normalizedX,
    required double time,
    required double energy,
    required double density,
    required bool isRightSide,
  }) {
    final effectiveDensity = density.clamp(0.0, 1.0);
    final drive = energy.clamp(0.0, 1.0);
    if (effectiveDensity <= _flatEpsilon || drive <= _flatEpsilon) {
      return (upper: 0.0, lower: 0.0);
    }

    final u = normalizedX.clamp(0.0, 1.0);
    final sideSeed = isRightSide ? 3.17 : 0.0;
    final t = time * math.pi * 2;

    final layerA = _microResonance(u, t, sideSeed);
    final layerB = _mediumOscillation(u, t, sideSeed);
    final layerC = _clusteredPeaks(u, t, sideSeed, effectiveDensity);
    final weights = layerWeightsForDensity(effectiveDensity);

    final nearCircleBoost = 0.55 + 0.45 * math.pow(1 - u, 0.42);
    final edgeTaper = 0.68 + 0.32 * math.pow(1 - u, 0.38);

    final combined = (layerA * weights.$1 +
            layerB * weights.$2 +
            layerC * weights.$3) *
        nearCircleBoost *
        edgeTaper *
        drive;

    final lowerBias =
        0.58 + _deterministicNoise(u * 91 + sideSeed, t) * 0.34;
    final upperWobble =
        0.92 + math.sin(u * 44 + t * _temporal(0.35) + sideSeed) * 0.08;

    return (
      upper: (combined * upperWobble).clamp(0.0, 1.0),
      lower: (combined * lowerBias).clamp(0.0, 1.0),
    );
  }

  /// Maximum combined upper+lower sample across [steps] positions.
  static double horizontalPeakAmplitude({
    required double time,
    required double energy,
    required double density,
    int steps = 48,
    bool isRightSide = false,
  }) {
    var peak = 0.0;
    for (var i = 0; i <= steps; i++) {
      final sample = horizontalWaveformSample(
        normalizedX: i / steps,
        time: time,
        energy: energy,
        density: density,
        isRightSide: isRightSide,
      );
      peak = math.max(peak, sample.upper + sample.lower);
    }
    return peak;
  }

  /// Smooth cluster activation weight for ordered cluster [clusterIndex].
  static double clusterActivationWeight(int clusterIndex, double density) {
    if (density <= _flatEpsilon) return 0.0;
    final threshold = (clusterIndex + 0.5) / clusterCount;
    return _smoothstep(
      threshold - _clusterFeather,
      threshold + _clusterFeather,
      density,
    );
  }

  /// Sum of cluster activation weights — richness proxy without hard counts.
  static double weightedClusterRichness(double density) {
    var sum = 0.0;
    for (var c = 0; c < clusterCount; c++) {
      sum += clusterActivationWeight(c, density);
    }
    return sum;
  }

  /// Layer weights derived continuously from interpolated density.
  static (double micro, double medium, double cluster) layerWeightsForDensity(
    double density,
  ) {
    if (density <= _flatEpsilon) {
      return (0.0, 0.0, 0.0);
    }
    final d = density.clamp(0.0, 1.0);
    return (
      0.30 + 0.28 * d,
      0.30 + 0.58 * d,
      0.24 + 0.76 * d,
    );
  }

  static double _temporal(double factor) =>
      factor * SediHorizontalResonanceProfile.temporalSpeed;

  static double _smoothstep(double edge0, double edge1, double x) {
    if (edge1 <= edge0) return x >= edge1 ? 1.0 : 0.0;
    final t = ((x - edge0) / (edge1 - edge0)).clamp(0.0, 1.0);
    return t * t * (3.0 - 2.0 * t);
  }

  /// Layer A — continuous micro-resonance across the full span.
  static double _microResonance(double u, double t, double sideSeed) {
    final a = math.sin(u * 286 + t * _temporal(1.0) + sideSeed).abs();
    final b = math.sin(u * 171 - t * _temporal(0.75) + sideSeed * 1.7).abs();
    final c = math.sin(u * 96 + t * _temporal(1.15) + sideSeed * 0.55).abs();
    return (a * 0.42 + b * 0.34 + c * 0.24) * 0.16;
  }

  /// Layer B — irregular medium-frequency groupings.
  static double _mediumOscillation(double u, double t, double sideSeed) {
    final hash = _deterministicNoise(u * 118 + sideSeed, t);
    final carrier =
        math.sin(u * 36 + t * _temporal(0.55) + hash * 3.2 + sideSeed);
    final grouping = math.pow(
      math.sin(u * 8.8 + t * _temporal(0.18) + sideSeed * 0.35),
      2,
    ).toDouble();
    final ripple = math.sin(u * 62 - t * _temporal(0.65) + hash * 5).abs();
    return (carrier.abs() * 0.55 + ripple * 0.45) *
        grouping *
        (0.24 + hash * 0.2);
  }

  /// Layer C — dense clustered peaks with gradual envelopes.
  static double _clusteredPeaks(
    double u,
    double t,
    double sideSeed,
    double density,
  ) {
    final gapTightening = 0.82 + density * 0.18;
    var peak = 0.0;
    for (var c = 0; c < clusterCount; c++) {
      final activation = clusterActivationWeight(c, density);
      if (activation <= _flatEpsilon) continue;

      final seed = c * 2.11 + sideSeed * 1.43;
      final drift =
          math.sin(t * _temporal(0.08 + c * 0.02) + seed) * 0.07;
      final center =
          0.06 + (math.sin(seed * 2.35 + t * _temporal(0.11)) + 1) * 0.44 + drift;
      final width = (0.055 + (c % 4) * 0.022) * gapTightening;
      final dist = (u - center).abs();
      final envelope = math.exp(-(dist * dist) / (width * width * 2.2));
      final hash = _deterministicNoise(u * 150 + c * 19.3 + sideSeed, t);
      final ripple = math.pow(
        math.max(
          0,
          math.sin(u * 88 - t * _temporal(0.95) + hash * 7 + seed),
        ),
        2.4,
      ).toDouble();
      final swell = math.pow(
        math.max(
          0,
          math.sin(u * 24 + t * _temporal(0.28) + hash * 4 + seed * 0.7),
        ),
        1.8,
      ).toDouble();
      peak = math.max(
        peak,
        envelope * (ripple * 0.68 + swell * 0.42) * activation,
      );
    }
    return peak;
  }

  static double _deterministicNoise(double seed, double phase) {
    final v = math.sin(
          seed * 12.9898 +
              phase * SediHorizontalResonanceProfile.temporalSpeed * 0.2,
        ) *
        43758.5453;
    return v - v.floorToDouble();
  }
}
