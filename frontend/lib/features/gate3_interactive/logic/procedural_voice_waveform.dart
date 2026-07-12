import 'dart:math' as math;

import '../models/gate3_interaction_state.dart';
import '../presentation/widgets/sedi_audio_visualizer_geometry.dart';

/// Deterministic procedural waveform energy for Gate 3 audio visualization.
///
/// Circular energy is state-independent (always restrained). Horizontal energy
/// is driven by caller-supplied [energy] and [state] for thinking/speaking
/// resonance. This is **not** synchronized to real TTS or playback amplitude.
class ProceduralVoiceWaveform {
  ProceduralVoiceWaveform._();

  static const int _horizontalClusterCount = 5;

  /// Radial bar length factor in `[0, 1]` for the circular spectrum.
  ///
  /// State-independent: restrained travelling clusters inside the idle envelope.
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

  /// Vertical peak amplitude for horizontal voice waveform samples.
  ///
  /// [normalizedX] is 0 at the circle tangent and 1 at the screen edge.
  static double horizontalPeakAmplitude({
    required double normalizedX,
    required double time,
    required double energy,
    required Gate3InteractionState state,
    required bool isRightSide,
  }) {
    if (energy <= 0.001) return 0;

    final sideSeed = isRightSide ? 2.71 : 0.0;
    final x = normalizedX.clamp(0.0, 1.0);
    final t = time * math.pi * 2;

    var peak = 0.0;
    for (var c = 0; c < _horizontalClusterCount; c++) {
      final clusterSeed = c * 1.93 + sideSeed * 1.37;
      final drift = math.sin(t * (0.12 + c * 0.04) + clusterSeed) * 0.08;
      final center =
          0.12 + (math.sin(clusterSeed * 2.7 + t * 0.18) + 1) * 0.38 + drift;
      final width = 0.035 + (c % 3) * 0.018;
      final dist = (x - center).abs();
      if (dist > width * 3.2) continue;

      final envelope =
          math.pow(math.max(0, 1 - dist / (width * 3.2)), 2.2).toDouble();
      final hash = _deterministicNoise(x * 140 + c * 23.7 + sideSeed, t);
      final spike = math.pow(
        math.max(
          0,
          math.sin(x * 210 - t * 16 + hash * 9 + c * 2.6 + sideSeed),
        ),
        4,
      ).toDouble();
      final burst = math.pow(
        math.max(0, math.sin(x * 48 + t * 4.8 + hash * 11 + clusterSeed)),
        3,
      ).toDouble();

      peak = math.max(peak, envelope * (spike * 0.72 + burst * 0.38));
    }

    final density = switch (state) {
      Gate3InteractionState.idle => 0.06,
      Gate3InteractionState.listening => 0.1,
      Gate3InteractionState.thinking => 0.48,
      Gate3InteractionState.speaking => 1.0,
    };

    return (peak * density * energy).clamp(0.0, 1.0);
  }

  /// Asymmetric lower spike factor for speech-like resonance (not mirrored).
  static double asymmetricLowerFactor({
    required double normalizedX,
    required bool isRightSide,
  }) {
    final sideSeed = isRightSide ? 1.9 : 0.4;
    final hash = _deterministicNoise(normalizedX * 88 + sideSeed, sideSeed);
    return (0.12 + hash * 0.22).clamp(0.08, 0.38);
  }

  static double _deterministicNoise(double seed, double time) {
    final v = math.sin(seed * 12.9898 + time * 0.37) * 43758.5453;
    return v - v.floorToDouble();
  }
}
