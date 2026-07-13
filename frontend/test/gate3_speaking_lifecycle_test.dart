import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/data/models/chat_message.dart';
import 'package:sedi_app/features/gate3_interactive/logic/gate3_orb_state_resolver.dart';
import 'package:sedi_app/features/gate3_interactive/logic/gate3_speaking_lifecycle.dart';
import 'package:sedi_app/features/gate3_interactive/models/gate3_interaction_state.dart';

List<ChatMessage> _messages(List<String> texts, {required bool assistant}) {
  return texts
      .map(
        (text) => assistant
            ? ChatMessage.assistant(text: text)
            : ChatMessage.user(text: text),
      )
      .toList();
}

void main() {
  group('Gate3SpeakingLifecycle', () {
    late Gate3SpeakingLifecycle lifecycle;

    setUp(() {
      lifecycle = Gate3SpeakingLifecycle();
    });

    String? consume({
      required int previousCount,
      required List<ChatMessage> messages,
      bool syncReady = true,
      bool isThinking = false,
    }) {
      return lifecycle.consumeSpeakingResponse(
        syncReady: syncReady,
        previousMessageCount: previousCount,
        currentMessageCount: messages.length,
        messages: messages,
        isThinking: isThinking,
      );
    }

    test('startup greeting remains idle', () {
      final messages = _messages(['Welcome to Sedi.'], assistant: true);
      expect(consume(previousCount: 0, messages: messages), isNull);
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

    test('restored history remains idle', () {
      final messages = <ChatMessage>[
        ChatMessage.user(text: 'Earlier user'),
        ChatMessage.assistant(text: 'Earlier assistant'),
        ChatMessage.assistant(text: 'Another assistant'),
      ];
      expect(consume(previousCount: 0, messages: messages), isNull);
      expect(consume(previousCount: 2, messages: messages), isNull);
    });

    test('pending user submission followed by one assistant message speaks once',
        () {
      lifecycle.markUserSubmission();
      final messages = _messages(['Hello'], assistant: false)
        ..add(ChatMessage.assistant(text: 'Fresh assistant reply.'));

      final response = consume(previousCount: 1, messages: messages);
      expect(response, 'Fresh assistant reply.');
      expect(lifecycle.awaitingAssistantResponse, isFalse);
    });

    test('batched user and assistant append activates speaking once', () {
      lifecycle.markUserSubmission();
      final messages = <ChatMessage>[
        ChatMessage.user(text: 'Hello'),
        ChatMessage.assistant(text: 'Fresh assistant reply.'),
      ];

      final response = consume(previousCount: 0, messages: messages);
      expect(response, 'Fresh assistant reply.');
      expect(lifecycle.awaitingAssistantResponse, isFalse);
    });

    test('batch with multiple assistant entries consumes pending once', () {
      lifecycle.markUserSubmission();
      final messages = <ChatMessage>[
        ChatMessage.user(text: 'Question'),
        ChatMessage.assistant(text: 'First part.'),
        ChatMessage.assistant(text: 'Final part.'),
      ];

      final response = consume(previousCount: 0, messages: messages);
      expect(response, 'Final part.');
      expect(lifecycle.awaitingAssistantResponse, isFalse);
      expect(
        consume(previousCount: messages.length, messages: messages),
        isNull,
      );
    });

    test('batched assistant entries without pending do not speak', () {
      final messages = <ChatMessage>[
        ChatMessage.assistant(text: 'One'),
        ChatMessage.assistant(text: 'Two'),
      ];
      expect(consume(previousCount: 0, messages: messages), isNull);
    });

    test('user-only batch does not speak', () {
      lifecycle.markUserSubmission();
      final messages = _messages(['Only user'], assistant: false);
      expect(consume(previousCount: 0, messages: messages), isNull);
      expect(lifecycle.awaitingAssistantResponse, isTrue);
    });

    test('pending is not cleared during pre-thinking false frame', () {
      lifecycle.markUserSubmission();
      lifecycle.onThinkingEndedWithoutAssistantResponse();
      expect(lifecycle.awaitingAssistantResponse, isTrue);
      expect(lifecycle.requestObservedThinking, isFalse);
    });

    test('observed thinking true to false with no response clears pending', () {
      lifecycle.markUserSubmission();
      lifecycle.onThinkingBecameTrue();
      lifecycle.onThinkingEndedWithoutAssistantResponse();
      expect(lifecycle.awaitingAssistantResponse, isFalse);
    });

    test('very fast assistant response before observed thinking consumes safely',
        () {
      lifecycle.markUserSubmission();
      final messages = _messages(['Reply'], assistant: false)
        ..add(ChatMessage.assistant(text: 'Fast reply.'));

      final response = consume(previousCount: 1, messages: messages);
      expect(response, 'Fast reply.');
      expect(lifecycle.awaitingAssistantResponse, isFalse);
      expect(lifecycle.requestObservedThinking, isFalse);
    });

    test('second unsolicited assistant message after consumption does not speak',
        () {
      lifecycle.markUserSubmission();
      final firstBatch = <ChatMessage>[
        ChatMessage.user(text: 'Hi'),
        ChatMessage.assistant(text: 'Answer'),
      ];
      expect(consume(previousCount: 0, messages: firstBatch), 'Answer');

      final secondBatch = List<ChatMessage>.from(firstBatch)
        ..add(ChatMessage.assistant(text: 'Unsolicited'));
      expect(
        consume(previousCount: firstBatch.length, messages: secondBatch),
        isNull,
      );
    });

    test('message list shrink does not speak', () {
      lifecycle.markUserSubmission();
      final messages = _messages(['Only user'], assistant: false);
      expect(
        lifecycle.consumeSpeakingResponse(
          syncReady: true,
          previousMessageCount: 3,
          currentMessageCount: messages.length,
          messages: messages,
          isThinking: false,
        ),
        isNull,
      );
    });

    test('retry lifecycle behaves like a new user submission', () {
      lifecycle.markUserSubmission();
      lifecycle.onThinkingBecameTrue();
      lifecycle.onThinkingEndedWithoutAssistantResponse();
      expect(lifecycle.awaitingAssistantResponse, isFalse);

      lifecycle.markUserSubmission();
      final messages = <ChatMessage>[
        ChatMessage.user(text: 'Retry'),
        ChatMessage.assistant(text: 'Retry answer'),
      ];
      expect(consume(previousCount: 0, messages: messages), 'Retry answer');
    });

    test('voice submission lifecycle behaves like text submission', () {
      lifecycle.markUserSubmission();
      final messages = <ChatMessage>[
        ChatMessage.user(text: '[voice]'),
        ChatMessage.assistant(text: 'Voice answer'),
      ];
      expect(consume(previousCount: 0, messages: messages), 'Voice answer');
    });

    test('speaking timer completion returns to idle', () {
      expect(
        lifecycle.shouldCompleteSpeakingVisual(
          speakingVisualActive: true,
          timerElapsed: true,
        ),
        isTrue,
      );
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
  });
}
