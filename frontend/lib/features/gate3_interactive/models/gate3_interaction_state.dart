enum Gate3InteractionState {
  /// Default / ready state.
  idle,

  /// User is interacting (typing or speaking).
  listening,

  /// Sedi is processing the request.
  thinking,

  /// Sedi is responding (voice in future).
  speaking,
}

