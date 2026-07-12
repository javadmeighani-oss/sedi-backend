import 'dart:math' as math;

import '../models/gate3_interaction_state.dart';

/// Deterministic procedural waveform energy for Gate 3 audio visualization.
///
/// This is **not** synchronized to real TTS or playback amplitude. When real
/// audio level metering becomes available, replace calls to
/// [horizontalWaveOffset] / [circularWaveEnergy] with measured samples while
/// keeping the painter API unchanged.
class ProceduralVoiceWaveform {
  ProceduralVoiceWaveform._();

  static double circularWaveEnergy({
    required double angle,
    required double time,
    required Gate3InteractionState state,
  }) {
    final speed = _circularSpeed(state);
    final t = time * speed;

    final fundamental = math.sin(angle * 4 + t * math.pi * 6);
    final harmonicA = math.sin(angle * 9 - t * math.pi * 4) * 0.55;
    final harmonicB = math.sin(angle * 15 + t * math.pi * 3) * 0.28;
    final envelope = 0.62 + math.sin(angle * 2 - t * math.pi * 2) * 0.18;

    var energy = (fundamental + harmonicA + harmonicB) / 1.83 * envelope;

    if (state == Gate3InteractionState.thinking) {
      final pulse = math.sin(angle * 1.5 - t * math.pi * 10);
      energy += pulse * 0.35;
    } else if (state == Gate3InteractionState.speaking) {
      final cadence = math.sin(t * math.pi * 5) * 0.25;
      final syllable = math.sin(angle * 6 + t * math.pi * 14) * 0.2;
      energy += cadence + syllable;
    }

    return energy.clamp(-1.0, 1.0);
  }

  /// Vertical offset for a horizontal waveform sample.
  ///
  /// [normalizedX] is 0 at the circle edge and 1 at the screen edge.
  static double horizontalWaveOffset({
    required double normalizedX,
    required double time,
    required double energy,
    required Gate3InteractionState state,
    required bool isRightSide,
  }) {
    final sideSign = isRightSide ? 1.0 : -1.0;
    final propagation = normalizedX * math.pi * (isRightSide ? 1 : -1);
    final t = time * _horizontalSpeed(state);

    final carrier = math.sin(propagation * 3.2 + t * math.pi * 8 + sideSign);
    final detail = math.sin(propagation * 7.1 - t * math.pi * 5) * 0.45;
    final voice =
        math.sin(propagation * 2.0 + t * math.pi * 11 + math.sin(t * 2.1)) *
            0.35;

    var combined = (carrier + detail + voice) / 1.55;

    if (state == Gate3InteractionState.speaking) {
      final cadence = math.sin(t * math.pi * 4.5) * 0.55;
      final burst = math.sin(propagation * 4.8 + t * math.pi * 16) * 0.35;
      combined = combined * (1.1 + cadence.abs()) + burst;
    } else if (state == Gate3InteractionState.listening) {
      combined *= 1.15;
    } else if (state == Gate3InteractionState.thinking) {
      combined *= 0.45;
    }

    return combined * energy;
  }

  static double _circularSpeed(Gate3InteractionState state) {
    switch (state) {
      case Gate3InteractionState.idle:
        return 1.0;
      case Gate3InteractionState.listening:
        return 1.35;
      case Gate3InteractionState.thinking:
        return 2.0;
      case Gate3InteractionState.speaking:
        return 1.75;
    }
  }

  static double _horizontalSpeed(Gate3InteractionState state) {
    switch (state) {
      case Gate3InteractionState.idle:
        return 0.85;
      case Gate3InteractionState.listening:
        return 1.2;
      case Gate3InteractionState.thinking:
        return 0.95;
      case Gate3InteractionState.speaking:
        return 1.65;
    }
  }
}
