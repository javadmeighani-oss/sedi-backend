import 'dart:math';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Canonical per-install mobile identity.
///
/// One stable id per app installation. Shared by gateway pairing and
/// PushDevice registration. Never derived from IMEI / Android ID / PII.
class MobileInstallIdStore {
  MobileInstallIdStore({FlutterSecureStorage? secure})
      : _secure = secure ?? const FlutterSecureStorage();

  /// Existing secure-storage key — do not rename; existing installs reuse it.
  static const storageKey = 'sedi_gateway_install_id_v1';

  final FlutterSecureStorage _secure;

  /// Generate once if absent; return persisted value across restarts.
  Future<String> getOrCreate() async {
    final existing = await _secure.read(key: storageKey);
    if (existing != null && existing.trim().length >= 8) {
      return existing.trim();
    }
    final created = generateHighEntropyInstallId();
    await _secure.write(key: storageKey, value: created);
    return created;
  }

  Future<String?> peek() async {
    final v = await _secure.read(key: storageKey);
    if (v == null || v.trim().isEmpty) return null;
    return v.trim();
  }

  /// Test helper — overwrite stored id.
  Future<void> writeForTest(String value) async {
    await _secure.write(key: storageKey, value: value);
  }

  Future<void> clearForTest() async {
    await _secure.delete(key: storageKey);
  }

  static String generateHighEntropyInstallId({Random? random}) {
    final r = random ?? Random.secure();
    final bytes = List<int>.generate(32, (_) => r.nextInt(256));
    return bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  }
}
