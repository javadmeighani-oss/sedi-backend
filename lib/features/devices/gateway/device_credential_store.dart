import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Per-device relay credential (X-DEVICE-TOKEN) — secure storage only.
class DeviceCredentialStore {
  DeviceCredentialStore({FlutterSecureStorage? secure})
      : _secure = secure ?? const FlutterSecureStorage();

  final FlutterSecureStorage _secure;

  static String _key(String deviceId) =>
      'sedi_device_token_v1_${deviceId.trim()}';

  Future<void> saveToken({
    required String deviceId,
    required String token,
  }) async {
    final t = token.trim();
    if (t.isEmpty) return;
    await _secure.write(key: _key(deviceId), value: t);
  }

  Future<String?> readToken(String deviceId) async {
    final v = await _secure.read(key: _key(deviceId));
    if (v == null || v.trim().isEmpty) return null;
    return v.trim();
  }

  Future<void> clearToken(String deviceId) async {
    await _secure.delete(key: _key(deviceId));
  }
}
