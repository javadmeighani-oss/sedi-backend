import 'dart:async';

import 'package:flutter/foundation.dart';

/// Bounded A2 CTA enable gate: valid → wait [delay] → enable.
///
/// Invalid disables immediately. Any new [signature] while valid cancels and
/// restarts the delay. Does not navigate; callers still require an explicit press.
///
/// [sync] never calls [notifyListeners] (safe inside setState). Only the
/// completion timer notifies so the UI can rebuild when the CTA becomes enabled.
class A2StableEnableController extends ChangeNotifier {
  A2StableEnableController({
    this.delay = const Duration(milliseconds: 300),
  });

  static const Duration targetDelay = Duration(milliseconds: 300);

  final Duration delay;

  Timer? _timer;
  Object? _signature;
  bool _enabled = false;

  bool get enabled => _enabled;

  /// Sync CTA readiness from a validity predicate and change signature.
  ///
  /// Returns true when [enabled] changed synchronously (typically false→true
  /// is async via timer; true→false on invalid is synchronous).
  bool sync({required bool isValid, required Object? signature}) {
    if (!isValid) {
      _cancelTimer();
      _signature = null;
      if (_enabled) {
        _enabled = false;
        return true;
      }
      return false;
    }

    if (_enabled && _signature == signature) {
      return false;
    }

    if (!_enabled &&
        _signature == signature &&
        _timer != null &&
        _timer!.isActive) {
      return false;
    }

    final wasEnabled = _enabled;
    _signature = signature;
    _enabled = false;
    _cancelTimer();
    _timer = Timer(delay, () {
      if (_enabled) return;
      _enabled = true;
      notifyListeners();
    });
    return wasEnabled;
  }

  void reset() {
    _cancelTimer();
    _signature = null;
    _enabled = false;
  }

  void _cancelTimer() {
    _timer?.cancel();
    _timer = null;
  }

  @override
  void dispose() {
    _cancelTimer();
    super.dispose();
  }
}
