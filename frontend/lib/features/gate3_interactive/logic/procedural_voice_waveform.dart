import 'dart:math' as math;

import '../models/gate3_interaction_state.dart';

/// Deterministic procedural waveform energy for Gate 3 audio visualization.
///
/// This is **not** synchronized to real TTS or playback amplitude. When real
/// audio level metering becomes available, replace calls to
/// [radialBarEnergy] / [horizontalPeakAmplitude] with measured samples while
/// keeping the painter API unchanged.
class ProceduralVoiceWaveform {
  ProceduralVoiceWaveform._();

  /// Radial bar length factor in `[0, 1]` for the circular spectrum.
  static double radialBarEnergy({
    required double angle,
    required double time,
    required Gate3InteractionState state,
  }) {
    final speed = _circularSpeed(state);
    final t = time * speed * math.pi * 2;
    final travel = angle - t * 0.85;

    final clusterA = math.pow(math.sin(travel * 3.4 + 0.8), 2).toDouble();
    final clusterB =
        math.pow(math.sin(travel * 5.1 - t * 0.35 + 1.4), 2).toDouble() * 0.55;
    final clusterC =
        math.pow(math.sin(travel * 8.2 + t * 0.2), 2).toDouble() * 0.28;

    var energy = clusterA + clusterB + clusterC;
    final micro = (math.sin(angle * 28 + t * 4) + 1) * 0.035;

    switch (state) {
      case Gate3InteractionState.idle:
        energy = energy * 0.42 + micro;
      case Gate3InteractionState.listening:
        energy = energy * 0.72 + micro * 1.4;
      case Gate3InteractionState.thinking:
        final pulse = math.pow(math.sin(travel * 2.2 - t * 1.6), 2).toDouble();
        energy = energy * 0.95 + pulse * 0.55 + micro;
      case Gate3InteractionState.speaking:
        energy = energy * 0.58 + micro * 1.1;
    }

    return energy.clamp(0.0, 1.0);
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

    final sideBias = isRightSide ? 0.17 : 0.0;
    final x = normalizedX.clamp(0.0, 1.0);
    final t = time * _horizontalSpeed(state) * math.pi * 2;

    final index = (x * 120 + sideBias).floor();
    final hash = math.sin(index * 12.9898 + sideBias * 78.233) * 43758.5453;
    final jitter = hash - hash.floorToDouble();

    final carrier = math.sin(x * 38 + t * 5.5 + sideBias * 3);
    final spike = math.pow(
      math.max(0, math.sin(x * 92 - t * 11 + jitter * 6)),
      3,
    ).toDouble();
    final burst = math.pow(
      math.max(0, math.sin(x * 21 + t * 3.2 + jitter * 9 + 1.1)),
      2,
    ).toDouble();

    var combined = (carrier.abs() * 0.18 + spike * 0.62 + burst * 0.34);

    switch (state) {
      case Gate3InteractionState.idle:
        combined *= 0.12 + jitter * 0.08;
      case Gate3InteractionState.listening:
        combined *= 0.42 + jitter * 0.12;
      case Gate3InteractionState.thinking:
        combined *= 0.16;
      case Gate3InteractionState.speaking:
        final cadence = 0.55 + math.sin(t * 2.4) * 0.25;
        combined *= cadence + jitter * 0.2;
    }

    return (combined * energy).clamp(0.0, 1.0);
  }

  static double _circularSpeed(Gate3InteractionState state) {
    switch (state) {
      case Gate3InteractionState.idle:
        return 0.75;
      case Gate3InteractionState.listening:
        return 1.05;
      case Gate3InteractionState.thinking:
        return 1.55;
      case Gate3InteractionState.speaking:
        return 0.95;
    }
  }

  static double _horizontalSpeed(Gate3InteractionState state) {
    switch (state) {
      case Gate3InteractionState.idle:
        return 0.7;
      case Gate3InteractionState.listening:
        return 1.15;
      case Gate3InteractionState.thinking:
        return 0.85;
      case Gate3InteractionState.speaking:
        return 1.75;
    }
  }
}
