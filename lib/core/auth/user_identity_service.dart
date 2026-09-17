import 'package:flutter/foundation.dart';

import '../auth/auth_service.dart';
import '../auth/auth_profile_service.dart';
import '../utils/user_profile_manager.dart';

class UserIdentityService {
  UserIdentityService._();

  static int? _cachedUserId;
  static Future<int?>? _inflightResolve;

  static Future<int?> resolveUserId({bool forceRefresh = false}) async {
    if (!forceRefresh) {
      // Persisted backend-confirmed profile wins over any prior memory cache.
      final profile = await UserProfileManager.loadProfile();
      if (profile.userId != null && profile.userId! > 0) {
        _cachedUserId = profile.userId;
        return _cachedUserId;
      }
      if (_cachedUserId != null && _cachedUserId! > 0) return _cachedUserId;
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

  /// Replace any prior cache with backend-confirmed `/auth/me` user id only.
  /// Does not invent identity; [userId] must come from confirmed profile.
  static void adoptBackendConfirmedUserId(int userId) {
    _inflightResolve = null;
    _cachedUserId = userId > 0 ? userId : null;
  }

  @visibleForTesting
  static int? debugCachedUserId => _cachedUserId;

  @visibleForTesting
  static void debugSetCachedUserId(int? userId) {
    _cachedUserId = userId;
    _inflightResolve = null;
  }
}
