import '../../../../data/models/chat_message.dart';

/// Tracks whether the orb may enter speaking for a live assistant reply.
///
/// Speaking requires a pending user submission and a newly appended assistant
/// message. Greeting, restored history, and unsolicited assistant inserts never
/// activate speaking.
class Gate3SpeakingLifecycle {
  bool _awaitingAssistantResponse = false;
  bool _requestObservedThinking = false;

  bool get awaitingAssistantResponse => _awaitingAssistantResponse;

  bool get requestObservedThinking => _requestObservedThinking;

  void markUserSubmission() {
    _awaitingAssistantResponse = true;
    _requestObservedThinking = false;
  }

  void onThinkingBecameTrue() {
    if (_awaitingAssistantResponse) {
      _requestObservedThinking = true;
    }
  }

  void clearPendingResponse() {
    _awaitingAssistantResponse = false;
    _requestObservedThinking = false;
  }

  /// Returns appended messages when the list grows at the end.
  static List<ChatMessage> appendedMessages({
    required List<ChatMessage> messages,
    required int previousMessageCount,
  }) {
    if (messages.length <= previousMessageCount) return const [];
    return messages.sublist(previousMessageCount);
  }

  /// Returns assistant text when a genuine post-user response should speak.
  ///
  /// Inspects all messages appended since [previousMessageCount]. Messages are
  /// appended at the end of [messages] by [ChatController].
  String? consumeSpeakingResponse({
    required bool syncReady,
    required int previousMessageCount,
    required int currentMessageCount,
    required List<ChatMessage> messages,
    required bool isThinking,
  }) {
    if (!syncReady || currentMessageCount < previousMessageCount) {
      return null;
    }

    final delta = currentMessageCount - previousMessageCount;
    if (delta <= 0 || !_awaitingAssistantResponse || isThinking) {
      return null;
    }

    final appended = appendedMessages(
      messages: messages,
      previousMessageCount: previousMessageCount,
    );
    if (appended.isEmpty) return null;

    final assistantTexts = appended
        .where((message) => message.isSedi)
        .map((message) => message.text.trim())
        .where((text) => text.isNotEmpty)
        .toList(growable: false);
    if (assistantTexts.isEmpty) return null;

    clearPendingResponse();
    return assistantTexts.last;
  }

  /// Clears pending only after thinking was observed and ended without a reply.
  void onThinkingEndedWithoutAssistantResponse() {
    if (!_awaitingAssistantResponse || !_requestObservedThinking) {
      return;
    }
    clearPendingResponse();
  }

  /// Whether speaking visual should end and return to idle.
  bool shouldCompleteSpeakingVisual({
    required bool speakingVisualActive,
    required bool timerElapsed,
  }) =>
      speakingVisualActive && timerElapsed;
}
