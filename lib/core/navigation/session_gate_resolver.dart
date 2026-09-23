import '../auth/auth_profile_service.dart';
import '../auth/auth_refresh_service.dart';
import '../auth/auth_service.dart';
import '../auth/user_identity_service.dart';
import '../health_subject/sedi_health_subject_controller.dart';
import '../network/api_response.dart';
import '../utils/user_profile_manager.dart';
import '../../data/dto/auth/me_profile.dart';
import 'app_gate.dart';

/// Outcome of cold-start session authority (local profile is cache only).
enum SessionResolveStatus {
  /// No stored access token → A2.
  noSession,

  /// GET /auth/me (after optional refresh) confirmed profile → A3.
  authenticated,

  /// Auth rejected after refresh attempt → cleared → A2.
  authInvalid,

  /// Network / backend unavailable; tokens preserved; stay on A1 retry.
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

  /// Cached session exists but backend did not confirm — do not go to A2 or A3.
  bool get stayOnStartup => status == SessionResolveStatus.backendUnavailable;
}

/// Single decision point: which gate should open after splash (A1 / Gate 1).
///
/// LOCAL_PROFILE = CACHE ONLY.
/// MANDATORY_BACKEND_REVALIDATION_FOR_EXISTING_SESSION = YES.
class SessionGateResolver {
  SessionGateResolver._();

  /// Returns Gate 3 only when backend confirms session.
  /// Transient unavailability returns Gate 1 (stay). Invalid/no session → Gate 2.
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
  ///     - authoritative invalid refresh → clear session → A2
  ///     - timeout/network/in-flight ambiguity → keep tokens → stay on A1
  ///   - network/5xx → backendUnavailable → stay on A1 (tokens kept)
  static Future<SessionResolveResult> resolveColdStart({
    AuthProfileService? profileService,
    Future<bool> Function()? tryRefresh,
    Future<AuthRefreshOutcome> Function()? refreshOnce,
  }) async {
    final hasToken = await AuthService.hasToken();
    if (!hasToken) {
      return const SessionResolveResult(
        status: SessionResolveStatus.noSession,
        nextGate: SediAppGate.login,
      );
    }

    final service = profileService ?? AuthProfileService();

    // First /auth/me — do not force-logout via ApiClient during splash.
    var me = await service.fetchMe(recoverSessionOn401: false);
    if (me.ok && me.data != null) {
      await service.cacheProfileFromBackend(me.data!);
      if (_profileMeetsGateRequirements(me.data!)) {
        return const SessionResolveResult(
          status: SessionResolveStatus.authenticated,
          nextGate: SediAppGate.heart,
        );
      }
      // Backend responded without session identity authority — treat as invalid.
      return const SessionResolveResult(
        status: SessionResolveStatus.authInvalid,
        nextGate: SediAppGate.login,
      );
    }

    if (_isUnauthorized(me)) {
      final outcome = await _resolveRefreshOutcome(
        tryRefresh: tryRefresh,
        refreshOnce: refreshOnce,
      );
      if (outcome == AuthRefreshOutcome.transientFailure) {
        return const SessionResolveResult(
          status: SessionResolveStatus.backendUnavailable,
          nextGate: SediAppGate.splash,
        );
      }
      if (outcome != AuthRefreshOutcome.success) {
        await _clearInvalidSession();
        return const SessionResolveResult(
          status: SessionResolveStatus.authInvalid,
          nextGate: SediAppGate.login,
        );
      }

      me = await service.fetchMe(recoverSessionOn401: false);
      if (me.ok && me.data != null) {
        await service.cacheProfileFromBackend(me.data!);
        if (_profileMeetsGateRequirements(me.data!)) {
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

    // Network / timeout / 5xx — do not clear tokens; do not admit to A3;
    // do not send a cached session to Login/OTP.
    return const SessionResolveResult(
      status: SessionResolveStatus.backendUnavailable,
      nextGate: SediAppGate.splash,
    );
  }

  /// Valid session requires mandatory backend revalidation (no local short-circuit).
  static Future<bool> hasValidSession({
    AuthProfileService? profileService,
    Future<bool> Function()? tryRefresh,
    Future<AuthRefreshOutcome> Function()? refreshOnce,
  }) async {
    final result = await resolveColdStart(
      profileService: profileService,
      tryRefresh: tryRefresh,
      refreshOnce: refreshOnce,
    );
    return result.isAuthenticated;
  }

  /// Injected `tryRefresh: false` stays authoritative-invalid for existing tests.
  /// Production uses [AuthRefreshService.refreshOnce] so timeout/network keep tokens.
  static Future<AuthRefreshOutcome> _resolveRefreshOutcome({
    Future<bool> Function()? tryRefresh,
    Future<AuthRefreshOutcome> Function()? refreshOnce,
  }) async {
    if (refreshOnce != null) return refreshOnce();
    if (tryRefresh != null) {
      return (await tryRefresh())
          ? AuthRefreshOutcome.success
          : AuthRefreshOutcome.invalidSession;
    }
    return AuthRefreshService.refreshOnce();
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

  static bool _profileMeetsGateRequirements(MeProfileDto me) {
    final hasPhone = me.phone != null && me.phone!.trim().isNotEmpty;
    return me.userId > 0 && hasPhone;
  }
}
