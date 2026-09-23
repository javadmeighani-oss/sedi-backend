import 'dart:math';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../../core/device/mobile_install_id_store.dart';

/// Stable per-install mobile gateway identity.
/// Delegates to [MobileInstallIdStore]; same secure-storage key/value.
class GatewayInstallIdStore {
  GatewayInstallIdStore({
    FlutterSecureStorage? secure,
    MobileInstallIdStore? store,
  }) : _store = store ?? MobileInstallIdStore(secure: secure);

  /// Preserved key name for existing callers/tests.
  static const storageKey = MobileInstallIdStore.storageKey;

  final MobileInstallIdStore _store;

  /// Generate once if absent; return persisted value across restarts.
  Future<String> getOrCreate() => _store.getOrCreate();

  Future<String?> peek() => _store.peek();

  /// Test helper — overwrite stored id.
  Future<void> writeForTest(String value) => _store.writeForTest(value);

  Future<void> clearForTest() => _store.clearForTest();

  static String generateHighEntropyInstallId({Random? random}) {
    return MobileInstallIdStore.generateHighEntropyInstallId(random: random);
  }
}
