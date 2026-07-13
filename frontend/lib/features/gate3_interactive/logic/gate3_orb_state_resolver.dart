import '../models/gate3_interaction_state.dart';

/// Authoritative Gate 3 orb interaction-state mapping.
class Gate3OrbStateResolver {
  Gate3OrbStateResolver._();

  /// Whether typed composer text should activate listening resonance.
  static bool composerActivatesListening(String text) =>
      text.trim().isNotEmpty;

  /// Resolves the orb visual state from chat/composer lifecycle signals.
  static Gate3InteractionState resolve({
    required bool isThinking,
    required bool speakingVisual,
    required bool isRecording,
    required bool composerHasMeaningfulText,
  }) {
    if (isThinking) return Gate3InteractionState.thinking;
    if (speakingVisual) return Gate3InteractionState.speaking;
    if (isRecording || composerHasMeaningfulText) {
      return Gate3InteractionState.listening;
    }
    return Gate3InteractionState.idle;
  }
}
