import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Auth token persistence for A1/A2-shared session paths.
///
/// Access + refresh tokens live in secure storage.
/// SharedPreferences is used only for one-time migration and non-secret prefs.
/// Legacy `user_secret_key` is NOT a session authority input.
class AuthService {
  static const String _tokenKey = 'auth_token';
  static const String _refreshTokenKey = 'auth_refresh_token';
  static const String _migratedFlagKey = 'auth_tokens_secure_migrated_v1';

  /// In-memory cache so the token is available immediately after OTP verify.
  static String? _memoryAccessToken;
  static String? _memoryRefreshToken;
  static bool _migrationAttempted = false;

  static const FlutterSecureStorage _secure = FlutterSecureStorage();

  /// Test-only reset of in-memory auth/migration state.
  static void resetForTest() {
    _memoryAccessToken = null;
    _memoryRefreshToken = null;
    _migrationAttempted = false;
  }

  static Future<void> _ensureMigrated() async {
    if (_migrationAttempted) return;
    _migrationAttempted = true;
    try {
      final prefs = await SharedPreferences.getInstance();
      if (prefs.getBool(_migratedFlagKey) == true) {
        return;
      }

      final legacyAccess = prefs.getString(_tokenKey);
      final legacyRefresh = prefs.getString(_refreshTokenKey);

      if (legacyAccess != null && legacyAccess.isNotEmpty) {
        await _secure.write(key: _tokenKey, value: legacyAccess);
        await prefs.remove(_tokenKey);
      }
      if (legacyRefresh != null && legacyRefresh.isNotEmpty) {
        await _secure.write(key: _refreshTokenKey, value: legacyRefresh);
        await prefs.remove(_refreshTokenKey);
      }

      // Do not treat legacy secret_key as session authority.
      // Leave value in place for bounded A3 legacy callers until follow-up.
      await prefs.setBool(_migratedFlagKey, true);
    } catch (_) {
      // Best-effort migration; subsequent reads still try secure storage.
    }
  }

  /// دریافت توکن احراز هویت
  static Future<String?> getToken() async {
    final cached = _memoryAccessToken;
    if (cached != null && cached.isNotEmpty) {
      return cached;
    }
    try {
      await _ensureMigrated();
      final secure = await _secure.read(key: _tokenKey);
      if (secure != null && secure.isNotEmpty) {
        _memoryAccessToken = secure;
        return secure;
      }
      // Bounded fallback for mid-migration race.
      final prefs = await SharedPreferences.getInstance();
      return prefs.getString(_tokenKey);
    } catch (e) {
      return null;
    }
  }

  /// ذخیره توکن احراز هویت
  static Future<bool> setToken(String token) async {
    try {
      if (token.isEmpty) {
        _memoryAccessToken = null;
        return false;
      }
      _memoryAccessToken = token;
      await _ensureMigrated();
      await _secure.write(key: _tokenKey, value: token);
      // Clear any leftover insecure copy.
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_tokenKey);
      return true;
    } catch (e) {
      return false;
    }
  }

  /// Refresh token for POST /auth/refresh and /auth/logout.
  static Future<String?> getRefreshToken() async {
    final cached = _memoryRefreshToken;
    if (cached != null && cached.isNotEmpty) {
      return cached;
    }
    try {
      await _ensureMigrated();
      final secure = await _secure.read(key: _refreshTokenKey);
      if (secure != null && secure.isNotEmpty) {
        _memoryRefreshToken = secure;
        return secure;
      }
      final prefs = await SharedPreferences.getInstance();
      return prefs.getString(_refreshTokenKey);
    } catch (e) {
      return null;
    }
  }

  static Future<bool> setRefreshToken(String token) async {
    try {
      if (token.isEmpty) {
        _memoryRefreshToken = null;
        return false;
      }
      _memoryRefreshToken = token;
      await _ensureMigrated();
      await _secure.write(key: _refreshTokenKey, value: token);
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_refreshTokenKey);
      return true;
    } catch (e) {
      return false;
    }
  }

  static Future<bool> clearRefreshToken() async {
    _memoryRefreshToken = null;
    try {
      await _secure.delete(key: _refreshTokenKey);
      final prefs = await SharedPreferences.getInstance();
      return await prefs.remove(_refreshTokenKey);
    } catch (e) {
      return false;
    }
  }

  /// Store access + refresh tokens from OTP verify or refresh response.
  static Future<void> setTokens({
    required String accessToken,
    String? refreshToken,
  }) async {
    await setToken(accessToken);
    if (refreshToken != null && refreshToken.isNotEmpty) {
      await setRefreshToken(refreshToken);
    }
  }

  /// حذف توکن (خروج از حساب)
  static Future<bool> clearToken() async {
    _memoryAccessToken = null;
    try {
      await _secure.delete(key: _tokenKey);
      final prefs = await SharedPreferences.getInstance();
      return await prefs.remove(_tokenKey);
    } catch (e) {
      return false;
    }
  }

  /// بررسی وجود توکن
  static Future<bool> hasToken() async {
    try {
      final token = await getToken();
      return token != null && token.isNotEmpty;
    } catch (e) {
      return false;
    }
  }

  // Non-secret display name prefs (not session authority).
  static const String _userNameKey = 'user_name';

  /// Legacy key — retained only for scrubbing; NOT session authority.
  static const String _secretKeyKey = 'user_secret_key';

  /// دریافت نام کاربر
  static Future<String?> getUserName() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getString(_userNameKey);
    } catch (e) {
      return null;
    }
  }

  /// ذخیره نام کاربر
  static Future<bool> setUserName(String userName) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return await prefs.setString(_userNameKey, userName);
    } catch (e) {
      return false;
    }
  }

  /// Legacy secret key storage (NOT session authority — JWT + /auth/me only).
  /// Retained for bounded A3 legacy query compatibility until a follow-up Gate.
  static Future<String?> getSecretKey() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getString(_secretKeyKey);
    } catch (e) {
      return null;
    }
  }

  /// Legacy writer — does not confer session authority.
  static Future<bool> setSecretKey(String secretKey) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return await prefs.setString(_secretKeyKey, secretKey);
    } catch (e) {
      return false;
    }
  }

  /// پاک کردن اطلاعات کاربر (logout)
  static Future<bool> clearUserData() async {
    _memoryAccessToken = null;
    _memoryRefreshToken = null;
    _migrationAttempted = false;
    try {
      await _secure.delete(key: _tokenKey);
      await _secure.delete(key: _refreshTokenKey);
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_userNameKey);
      await prefs.remove(_secretKeyKey);
      await prefs.remove(_tokenKey);
      await prefs.remove(_refreshTokenKey);
      return true;
    } catch (e) {
      return false;
    }
  }
}
