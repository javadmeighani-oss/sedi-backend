import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/gate3_interactive/logic/gate3_orb_state_resolver.dart';
import 'package:sedi_app/features/gate3_interactive/models/gate3_interaction_state.dart';

void main() {
  group('Gate3OrbStateResolver', () {
    test('empty composer maps to idle', () {
      expect(
        Gate3OrbStateResolver.resolve(
          isThinking: false,
          speakingVisual: false,
          isRecording: false,
          composerHasMeaningfulText: false,
        ),
        Gate3InteractionState.idle,
      );
    });

    test('non-empty composer maps to listening', () {
      expect(
        Gate3OrbStateResolver.resolve(
          isThinking: false,
          speakingVisual: false,
          isRecording: false,
          composerHasMeaningfulText: true,
        ),
        Gate3InteractionState.listening,
      );
      expect(Gate3OrbStateResolver.composerActivatesListening('سلام'), isTrue);
    });

    test('clearing composer returns to idle', () {
      expect(Gate3OrbStateResolver.composerActivatesListening('   '), isFalse);
      expect(
        Gate3OrbStateResolver.resolve(
          isThinking: false,
          speakingVisual: false,
          isRecording: false,
          composerHasMeaningfulText:
              Gate3OrbStateResolver.composerActivatesListening(''),
        ),
        Gate3InteractionState.idle,
      );
    });

    test('send maps to thinking', () {
      expect(
        Gate3OrbStateResolver.resolve(
          isThinking: true,
          speakingVisual: false,
          isRecording: false,
          composerHasMeaningfulText: false,
        ),
        Gate3InteractionState.thinking,
      );
    });

    test('assistant presentation maps to speaking', () {
      expect(
        Gate3OrbStateResolver.resolve(
          isThinking: false,
          speakingVisual: true,
          isRecording: false,
          composerHasMeaningfulText: false,
        ),
        Gate3InteractionState.speaking,
      );
    });

    test('restored history does not create speaking without live visual', () {
      expect(
        Gate3OrbStateResolver.resolve(
          isThinking: false,
          speakingVisual: false,
          isRecording: false,
          composerHasMeaningfulText: false,
        ),
        Gate3InteractionState.idle,
      );
    });

    test('thinking outranks speaking visual', () {
      expect(
        Gate3OrbStateResolver.resolve(
          isThinking: true,
          speakingVisual: true,
          isRecording: false,
          composerHasMeaningfulText: false,
        ),
        Gate3InteractionState.thinking,
      );
    });

    test('recording maps to listening', () {
      expect(
        Gate3OrbStateResolver.resolve(
          isThinking: false,
          speakingVisual: false,
          isRecording: true,
          composerHasMeaningfulText: false,
        ),
        Gate3InteractionState.listening,
      );
    });
  });
}
