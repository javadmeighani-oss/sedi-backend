import '../auth/auth_service.dart';
import '../auth/auth_profile_service.dart';
import '../utils/user_profile_manager.dart';

class UserIdentityService {
  UserIdentityService._();

  static int? _cachedUserId;
  static Future<int?>? _inflightResolve;

  static Future<int?> resolveUserId({bool forceRefresh = false}) async {
    if (!forceRefresh) {
      if (_cachedUserId != null && _cachedUserId! > 0) return _cachedUserId;
      final profile = await UserProfileManager.loadProfile();
      if (profile.userId != null && profile.userId! > 0) {
        _cachedUserId = profile.userId;
        return _cachedUserId;
      }
    }

    if (_inflightResolve != null) return _inflightResolve;
    _inflightResolve = _resolveViaAuthMe();
    final result = await _inflightResolve;
    _inflightResolve = null;
    return result;
  }

  static Future<int?> _resolveViaAuthMe() async {
    final token = await AuthService.getToken();
    if (token == null || token.isEmpty) return null;

    final profileService = AuthProfileService();
    final me = await profileService.fetchAndCacheProfile();
    if (!me.ok || me.data == null) return null;

    final userId = me.data!.userId;
    if (userId <= 0) return null;

    _cachedUserId = userId;
    return userId;
  }

  /// Clear in-memory cache (call on logout / forced session reset).
  static void clearCache() {
    _cachedUserId = null;
    _inflightResolve = null;
  }
}
