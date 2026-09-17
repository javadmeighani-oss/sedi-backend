import '../auth/auth_profile_service.dart';
import '../auth/auth_refresh_service.dart';
import '../auth/auth_service.dart';
import '../auth/user_identity_service.dart';
import '../health_subject/sedi_health_subject_controller.dart';
import '../network/api_response.dart';
import '../utils/user_profile_manager.dart';
import '../../data/dto/auth/me_profile.dart';
import '../../data/models/user_profile.dart';
import 'app_gate.dart';

/// Outcome of cold-start session authority (local profile is cache only).
enum SessionResolveStatus {
  /// No stored access token → A2.
  noSession,

  /// GET /auth/me (after optional refresh) confirmed profile → A3.
  authenticated,

  /// Auth rejected after refresh attempt → cleared → A2.
  authInvalid,

  /// Network / backend unavailable; tokens preserved; controlled UX → A2.
  backendUnavailable,
}

class SessionResolveResult {
  const SessionResolveResult({
    required this.status,
    required this.nextGate,
  });

  final SessionResolveStatus status;
  final SediAppGate nextGate;

  bool get isAuthenticated => status == SessionResolveStatus.authenticated;
}

/// Single decision point: which gate should open after splash (A1 / Gate 1).
///
/// LOCAL_PROFILE = CACHE ONLY.
/// MANDATORY_BACKEND_REVALIDATION_FOR_EXISTING_SESSION = YES.
class SessionGateResolver {
  SessionGateResolver._();

  /// Returns Gate 3 only when backend confirms session; otherwise Gate 2.
  static Future<SediAppGate> resolveAfterSplash() async {
    final result = await resolveColdStart();
    return result.nextGate;
  }

  /// Cold-start authority path used by A1.
  ///
  /// Flow:
  /// - no token → A2
  /// - token present → GET /auth/me (recoverSessionOn401: false)
  ///   - 200 + profile ok → A3
  ///   - 401 → POST /auth/refresh → retry /auth/me
  ///     - success → A3
  ///     - fail → clear session → A2
  ///   - network/5xx → backendUnavailable → A2 (tokens kept)
  static Future<SessionResolveResult> resolveColdStart({
    AuthProfileService? profileService,
    Future<bool> Function()? tryRefresh,
  }) async {
    final hasToken = await AuthService.hasToken();
    if (!hasToken) {
      return const SessionResolveResult(
        status: SessionResolveStatus.noSession,
        nextGate: SediAppGate.login,
      );
    }

    final service = profileService ?? AuthProfileService();
    final refresh = tryRefresh ?? AuthRefreshService.tryRefresh;

    // First /auth/me — do not force-logout via ApiClient during splash.
    var me = await service.fetchMe(recoverSessionOn401: false);
    if (me.ok && me.data != null) {
      await service.cacheProfileFromBackend(me.data!);
      if (_profileMeetsGateRequirements(await UserProfileManager.loadProfile())) {
        return const SessionResolveResult(
          status: SessionResolveStatus.authenticated,
          nextGate: SediAppGate.heart,
        );
      }
      // Backend responded but profile incomplete — treat as invalid for A3.
      return const SessionResolveResult(
        status: SessionResolveStatus.authInvalid,
        nextGate: SediAppGate.login,
      );
    }

    if (_isUnauthorized(me)) {
      final refreshed = await refresh();
      if (!refreshed) {
        await _clearInvalidSession();
        return const SessionResolveResult(
          status: SessionResolveStatus.authInvalid,
          nextGate: SediAppGate.login,
        );
      }

      me = await service.fetchMe(recoverSessionOn401: false);
      if (me.ok && me.data != null) {
        await service.cacheProfileFromBackend(me.data!);
        if (_profileMeetsGateRequirements(
            await UserProfileManager.loadProfile())) {
          return const SessionResolveResult(
            status: SessionResolveStatus.authenticated,
            nextGate: SediAppGate.heart,
          );
        }
      }

      if (_isUnauthorized(me) || (me.ok && me.data == null)) {
        await _clearInvalidSession();
        return const SessionResolveResult(
          status: SessionResolveStatus.authInvalid,
          nextGate: SediAppGate.login,
        );
      }
    }

    // Network / timeout / 5xx — do not clear tokens; do not admit to A3.
    return const SessionResolveResult(
      status: SessionResolveStatus.backendUnavailable,
      nextGate: SediAppGate.login,
    );
  }

  /// Valid session requires mandatory backend revalidation (no local short-circuit).
  static Future<bool> hasValidSession({
    AuthProfileService? profileService,
    Future<bool> Function()? tryRefresh,
  }) async {
    final result = await resolveColdStart(
      profileService: profileService,
      tryRefresh: tryRefresh,
    );
    return result.isAuthenticated;
  }

  static bool _isUnauthorized(ApiResponse<MeProfileDto> me) {
    return me.statusCode == 401;
  }

  static Future<void> _clearInvalidSession() async {
    await AuthService.clearUserData();
    await UserProfileManager.clearProfile();
    UserIdentityService.clearCache();
    SediHealthSubjectController.instance.clearSessionState();
    // Avoid navigator side-effects during splash; Intro routes explicitly.
  }

  static bool _profileMeetsGateRequirements(UserProfile profile) {
    final hasPhone =
        profile.phoneNumber != null && profile.phoneNumber!.trim().isNotEmpty;
    final hasUserId = profile.userId != null && profile.userId! > 0;
    return hasUserId && profile.isVerified && hasPhone;
  }
}
