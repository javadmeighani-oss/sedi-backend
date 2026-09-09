import 'package:shared_preferences/shared_preferences.dart';

/// سرویس مدیریت احراز هویت
///
/// این کلاس برای مدیریت توکن احراز هویت کاربر استفاده می‌شود.
/// توکن در SharedPreferences ذخیره می‌شود.
class AuthService {
  static const String _tokenKey = 'auth_token';
  static const String _refreshTokenKey = 'auth_refresh_token';

  /// In-memory cache so the token is available immediately after OTP verify.
  static String? _memoryAccessToken;
  static String? _memoryRefreshToken;

  /// دریافت توکن احراز هویت
  ///
  /// Returns: توکن احراز هویت یا null در صورت عدم وجود
  static Future<String?> getToken() async {
    final cached = _memoryAccessToken;
    if (cached != null && cached.isNotEmpty) {
      return cached;
    }
    try {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getString(_tokenKey);
    } catch (e) {
      // در صورت خطا، null برمی‌گرداند
      return null;
    }
  }

  /// ذخیره توکن احراز هویت
  ///
  /// [token] توکن احراز هویت برای ذخیره
  /// Returns: true در صورت موفقیت، false در صورت خطا
  static Future<bool> setToken(String token) async {
    try {
      if (token.isEmpty) {
        _memoryAccessToken = null;
        return false;
      }
      _memoryAccessToken = token;
      final prefs = await SharedPreferences.getInstance();
      return await prefs.setString(_tokenKey, token);
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
      final prefs = await SharedPreferences.getInstance();
      return await prefs.setString(_refreshTokenKey, token);
    } catch (e) {
      return false;
    }
  }

  static Future<bool> clearRefreshToken() async {
    _memoryRefreshToken = null;
    try {
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
  ///
  /// Returns: true در صورت موفقیت، false در صورت خطا
  static Future<bool> clearToken() async {
    _memoryAccessToken = null;
    try {
      final prefs = await SharedPreferences.getInstance();
      return await prefs.remove(_tokenKey);
    } catch (e) {
      return false;
    }
  }

  /// بررسی وجود توکن
  ///
  /// Returns: true اگر توکن وجود داشته باشد، false در غیر این صورت
  static Future<bool> hasToken() async {
    try {
      final token = await getToken();
      return token != null && token.isNotEmpty;
    } catch (e) {
      return false;
    }
  }

  // User credentials for backend authentication
  static const String _userNameKey = 'user_name';
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

  /// دریافت secret key کاربر
  static Future<String?> getSecretKey() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getString(_secretKeyKey);
    } catch (e) {
      return null;
    }
  }

  /// ذخیره secret key کاربر
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
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_userNameKey);
      await prefs.remove(_secretKeyKey);
      await clearToken();
      await clearRefreshToken();
      return true;
    } catch (e) {
      return false;
    }
  }
}
