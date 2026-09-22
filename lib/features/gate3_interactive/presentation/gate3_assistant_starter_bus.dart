import 'dart:async';

/// Presentation-only Lifestyle→A3 handoff: insert a contextual assistant
/// starter into the canonical chat transcript. Never seeds the composer,
/// never auto-sends, never marks SPEAKING.
class Gate3AssistantStarterBus {
  Gate3AssistantStarterBus._();
  static final Gate3AssistantStarterBus instance = Gate3AssistantStarterBus._();

  final StreamController<String> _controller =
      StreamController<String>.broadcast();

  Stream<String> get stream => _controller.stream;

  void publish(String message) {
    final trimmed = message.trim();
    if (trimmed.isEmpty || _controller.isClosed) return;
    _controller.add(trimmed);
  }
}
