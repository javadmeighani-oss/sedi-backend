import 'dart:async';

/// Presentation-only handoff: Lifestyle CTAs seed the canonical A3 composer.
/// Never auto-sends; never inserts into transcript.
class Gate3ComposerDraftBus {
  Gate3ComposerDraftBus._();
  static final Gate3ComposerDraftBus instance = Gate3ComposerDraftBus._();

  final StreamController<String> _controller =
      StreamController<String>.broadcast();

  Stream<String> get stream => _controller.stream;

  void publish(String draft) {
    final trimmed = draft.trim();
    if (trimmed.isEmpty || _controller.isClosed) return;
    _controller.add(trimmed);
  }
}
