import 'dart:math' as math;

import '../presentation/widgets/sedi_audio_visualizer_geometry.dart';

/// Deterministic procedural waveform energy for Gate 3 audio visualization.
///
/// Circular energy is state-independent. Horizontal resonance uses a single
/// low-frequency cluster field rendered as discrete vertical bars.
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

  /// Normalized upper/lower bar half-lengths for one horizontal position.
  ///
  /// [normalizedX] is 0 at the circle tangent and 1 at the screen edge.
  /// [time] is horizontal phase in cycle units.
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

    final clusterField =
        _clusterField(u, t, sideSeed, effectiveDensity);
    final broadWave = _broadSpatialWave(u, t, sideSeed);
    final richness = 0.34 + effectiveDensity * 0.66;

    final nearCircleBoost = 0.58 + 0.42 * math.pow(1 - u, 0.45);
    final edgeTaper = 0.72 + 0.28 * math.pow(1 - u, 0.36);

    final combined = (clusterField * 0.78 + broadWave * 0.22) *
        richness *
        nearCircleBoost *
        edgeTaper *
        drive;

    final lowerBias =
        0.62 + math.sin(u * 5.4 + sideSeed * 0.7 + t * 0.22) * 0.14;
    final upperBias =
        0.88 + math.sin(u * 4.1 + sideSeed * 1.1 - t * 0.18) * 0.10;

    return (
      upper: (combined * upperBias).clamp(0.0, 1.0),
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

  /// Mean combined upper+lower amplitude across [steps] positions.
  static double horizontalMeanAmplitude({
    required double time,
    required double energy,
    required double density,
    int steps = 48,
    bool isRightSide = false,
  }) {
    var sum = 0.0;
    for (var i = 0; i <= steps; i++) {
      final sample = horizontalWaveformSample(
        normalizedX: i / steps,
        time: time,
        energy: energy,
        density: density,
        isRightSide: isRightSide,
      );
      sum += sample.upper + sample.lower;
    }
    return sum / (steps + 1);
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

  static double _smoothstep(double edge0, double edge1, double x) {
    if (edge1 <= edge0) return x >= edge1 ? 1.0 : 0.0;
    final t = ((x - edge0) / (edge1 - edge0)).clamp(0.0, 1.0);
    return t * t * (3.0 - 2.0 * t);
  }

  /// Seven broad Gaussian clusters with continuous density activation.
  static double _clusterField(
    double u,
    double t,
    double sideSeed,
    double density,
  ) {
    final gapTightening = 0.80 + density * 0.20;
    var field = 0.0;
    for (var c = 0; c < clusterCount; c++) {
      final activation = clusterActivationWeight(c, density);
      if (activation <= _flatEpsilon) continue;

      final seed = c * 1.73 + sideSeed * 1.29;
      final drift = math.sin(t * 0.32 + seed) * 0.045;
      final anchor = (c + 0.5) / clusterCount;
      final center =
          0.06 + anchor * 0.86 + math.sin(seed * 1.55 + t * 0.14) * 0.05 + drift;
      final width = (0.10 + (c % 3) * 0.016) * gapTightening;
      final dist = (u - center).abs();
      final envelope = math.exp(-(dist * dist) / (2 * width * width));

      final swell = math.pow(
        math.max(0, math.sin(u * 4.8 + t * 0.42 + seed * 0.6)),
        1.6,
      ).toDouble();

      field = math.max(field, envelope * (0.55 + swell * 0.45) * activation);
    }
    return field.clamp(0.0, 1.0);
  }

  /// Low-frequency spatial carrier shared by all active states.
  static double _broadSpatialWave(double u, double t, double sideSeed) {
    final a = math.sin(u * math.pi * 1.8 + sideSeed * 0.35 + t * 0.28);
    final b = math.sin(u * math.pi * 0.9 - t * 0.22 + sideSeed * 0.55);
    return ((a + 1) * 0.32 + (b + 1) * 0.18).clamp(0.0, 1.0);
  }
}
