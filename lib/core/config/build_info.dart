import 'package:flutter/foundation.dart';

/// Debug-only build label to confirm which frontend commit is installed.
class BuildInfo {
  BuildInfo._();

  /// Set in CI or local debug builds; empty in release if not configured.
  static const String gateLabel = String.fromEnvironment(
    'SEDI_GATE_BUILD_LABEL',
    defaultValue: 'gate2-dev',
  );

  static void logDebugLabel() {
    if (!kDebugMode) return;
    debugPrint('[BuildInfo] gate=$gateLabel');
  }
}
