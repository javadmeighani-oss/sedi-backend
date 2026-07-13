import 'dart:math' as math;

import '../models/gate3_interaction_state.dart';
import '../presentation/widgets/sedi_audio_visualizer_geometry.dart';

/// Deterministic procedural waveform energy for Gate 3 audio visualization.
///
/// Circular energy is state-independent. Horizontal resonance uses three
/// simultaneous layers (micro, medium, clustered peaks) and is **not**
/// synchronized to real TTS or playback amplitude.
class ProceduralVoiceWaveform {
  ProceduralVoiceWaveform._();

  static const int _clusterCount = 7;

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
  static ({double upper, double lower}) horizontalWaveformSample({
    required double normalizedX,
    required double time,
    required double energy,
    required Gate3InteractionState state,
    required bool isRightSide,
  }) {
    final u = normalizedX.clamp(0.0, 1.0);
    final sideSeed = isRightSide ? 3.17 : 0.0;
    final t = time * math.pi * 2;
    final drive = energy.clamp(0.08, 1.0);

    final layerA = _microResonance(u, t, sideSeed);
    final layerB = _mediumOscillation(u, t, sideSeed);
    final layerC = _clusteredPeaks(u, t, sideSeed);
    final weights = _layerWeights(state);

    final nearCircleBoost = 0.55 + 0.45 * math.pow(1 - u, 0.42);
    final edgeTaper = 0.68 + 0.32 * math.pow(1 - u, 0.38);

    final combined = (layerA * weights.$1 +
            layerB * weights.$2 +
            layerC * weights.$3) *
        nearCircleBoost *
        edgeTaper *
        drive;

    final lowerBias =
        0.58 + _deterministicNoise(u * 91 + sideSeed, t * 0.41) * 0.34;
    final upperWobble =
        0.92 + math.sin(u * 44 + t * 2.1 + sideSeed) * 0.08;

    return (
      upper: (combined * upperWobble).clamp(0.0, 1.0),
      lower: (combined * lowerBias).clamp(0.0, 1.0),
    );
  }

  /// Layer A — continuous micro-resonance across the full span.
  static double _microResonance(double u, double t, double sideSeed) {
    final a = math.sin(u * 286 + t * 8.6 + sideSeed).abs();
    final b = math.sin(u * 171 - t * 5.4 + sideSeed * 1.7).abs();
    final c = math.sin(u * 96 + t * 11.4 + sideSeed * 0.55).abs();
    return 0.18 + (a * 0.42 + b * 0.34 + c * 0.24) * 0.16;
  }

  /// Layer B — irregular medium-frequency groupings.
  static double _mediumOscillation(double u, double t, double sideSeed) {
    final hash = _deterministicNoise(u * 118 + sideSeed, t);
    final carrier = math.sin(u * 36 + t * 2.6 + hash * 3.2 + sideSeed);
    final grouping = math.pow(
      math.sin(u * 8.8 + t * 0.72 + sideSeed * 0.35),
      2,
    ).toDouble();
    final ripple = math.sin(u * 62 - t * 4.1 + hash * 5).abs();
    return (carrier.abs() * 0.55 + ripple * 0.45) *
        grouping *
        (0.24 + hash * 0.2);
  }

  /// Layer C — dense clustered peaks with gradual envelopes.
  static double _clusteredPeaks(double u, double t, double sideSeed) {
    var peak = 0.0;
    for (var c = 0; c < _clusterCount; c++) {
      final seed = c * 2.11 + sideSeed * 1.43;
      final drift = math.sin(t * (0.1 + c * 0.035) + seed) * 0.07;
      final center =
          0.06 + (math.sin(seed * 2.35 + t * 0.13) + 1) * 0.44 + drift;
      final width = 0.055 + (c % 4) * 0.022;
      final dist = (u - center).abs();
      final envelope = math.exp(-(dist * dist) / (width * width * 2.2));
      final hash = _deterministicNoise(u * 150 + c * 19.3 + sideSeed, t);
      final ripple = math.pow(
        math.max(0, math.sin(u * 88 - t * 12.5 + hash * 7 + seed)),
        2.4,
      ).toDouble();
      final swell = math.pow(
        math.max(0, math.sin(u * 24 + t * 3.6 + hash * 4 + seed * 0.7)),
        1.8,
      ).toDouble();
      peak = math.max(peak, envelope * (ripple * 0.68 + swell * 0.42));
    }
    return peak;
  }

  static (double micro, double medium, double cluster) _layerWeights(
    Gate3InteractionState state,
  ) {
    return switch (state) {
      Gate3InteractionState.idle => (1.0, 0.28, 0.14),
      Gate3InteractionState.listening => (1.0, 0.42, 0.22),
      Gate3InteractionState.thinking => (1.0, 0.72, 0.58),
      Gate3InteractionState.speaking => (1.0, 0.92, 1.0),
    };
  }

  static double _deterministicNoise(double seed, double time) {
    final v = math.sin(seed * 12.9898 + time * 0.37) * 43758.5453;
    return v - v.floorToDouble();
  }
}
