import 'dart:io';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/auth/auth_profile_service.dart';
import 'package:sedi_app/core/auth/auth_service.dart';
import 'package:sedi_app/core/auth/user_identity_service.dart';
import 'package:sedi_app/core/health_subject/sedi_health_subject.dart';
import 'package:sedi_app/core/health_subject/sedi_health_subject_controller.dart';
import 'package:sedi_app/core/navigation/app_gate.dart';
import 'package:sedi_app/core/navigation/session_gate_resolver.dart';
import 'package:sedi_app/core/network/api_error.dart';
import 'package:sedi_app/core/network/api_response.dart';
import 'package:sedi_app/core/utils/user_profile_manager.dart';
import 'package:sedi_app/data/dto/auth/me_profile.dart';
import 'package:sedi_app/data/models/user_profile.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/gate3_localization.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _FakeAuthProfileService extends AuthProfileService {
  _FakeAuthProfileService(this._responses);

  final List<ApiResponse<MeProfileDto>> _responses;
  int fetchCount = 0;

  @override
  Future<ApiResponse<MeProfileDto>> fetchMe({
    String? accessToken,
    bool recoverSessionOn401 = true,
  }) async {
    final idx = fetchCount.clamp(0, _responses.length - 1);
    fetchCount++;
    return _responses[idx];
  }
}

MeProfileDto _me(int userId) => MeProfileDto(
      userId: userId,
      phone: '+989121234567',
      name: 'User$userId',
      preferredLanguage: 'en',
    );

ApiResponse<MeProfileDto> _unauthorized() => ApiResponse<MeProfileDto>(
      ok: false,
      error: const ApiError(code: 'UNAUTHORIZED', message: '401'),
      statusCode: 401,
    );

ApiResponse<MeProfileDto> _network() => ApiResponse<MeProfileDto>(
      ok: false,
      error: const ApiError(code: 'NETWORK_ERROR', message: 'offline'),
      statusCode: null,
    );

String _readLib(String relativePath) {
  final file = File('lib/$relativePath');
  expect(file.existsSync(), isTrue, reason: relativePath);
  return file.readAsStringSync();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
    AuthService.resetForTest();
    await AuthService.clearUserData();
    await UserProfileManager.clearProfile();
    UserIdentityService.clearCache();
    SediHealthSubjectController.instance.debugResetForTest();
  });

  group('R1 invalid-session identity clear', () {
    test('invalid session clears UserIdentityService cache', () async {
      await AuthService.setTokens(
        accessToken: 'expired',
        refreshToken: 'bad-refresh',
      );
      UserIdentityService.debugSetCachedUserId(111);

      final result = await SessionGateResolver.resolveColdStart(
        profileService: _FakeAuthProfileService([_unauthorized()]),
        tryRefresh: () async => false,
      );

      expect(result.status, SessionResolveStatus.authInvalid);
      expect(result.nextGate, SediAppGate.login);
      expect(await AuthService.hasToken(), isFalse);
      expect(UserIdentityService.debugCachedUserId(), isNull);
    });

    test('invalid session also clears HealthSubject presentation state',
        () async {
      await AuthService.setTokens(
        accessToken: 'expired',
        refreshToken: 'bad-refresh',
      );
      SediHealthSubjectController.instance.debugSeedForTest(subjects: [
        const SediHealthSubject(
          id: 1,
          displayName: 'Me',
          subjectKind: 'self',
          status: 'active',
          accessRole: 'SELF',
        ),
      ]);

      await SessionGateResolver.resolveColdStart(
        profileService: _FakeAuthProfileService([_unauthorized()]),
        tryRefresh: () async => false,
      );

      final c = SediHealthSubjectController.instance;
      expect(c.accessibleSubjects, isEmpty);
      expect(c.activeSubject, isNull);
    });

    test('backendUnavailable keeps tokens and does not clear identity',
        () async {
      await AuthService.setTokens(
        accessToken: 'access',
        refreshToken: 'refresh',
      );
      UserIdentityService.debugSetCachedUserId(42);
      SediHealthSubjectController.instance.debugSeedForTest(subjects: [
        const SediHealthSubject(
          id: 7,
          displayName: 'Me',
          subjectKind: 'self',
          status: 'active',
          accessRole: 'SELF',
        ),
      ]);

      final result = await SessionGateResolver.resolveColdStart(
        profileService: _FakeAuthProfileService([_network()]),
      );

      expect(result.status, SessionResolveStatus.backendUnavailable);
      expect(result.stayOnStartup, isTrue);
      expect(result.nextGate, isNot(SediAppGate.login));
      expect(result.nextGate, isNot(SediAppGate.heart));
      expect(await AuthService.hasToken(), isTrue);
      expect(UserIdentityService.debugCachedUserId(), 42);
      expect(SediHealthSubjectController.instance.activeSubject?.id, 7);
    });
  });

  group('R1 post-OTP / backend-confirmed identity reconciliation', () {
    test('cacheProfileFromBackend replaces stale cached user id', () async {
      UserIdentityService.debugSetCachedUserId(111);
      await AuthProfileService().cacheProfileFromBackend(_me(222));

      expect(UserIdentityService.debugCachedUserId(), 222);
      final profile = await UserProfileManager.loadProfile();
      expect(profile.userId, 222);
    });

    test('account A → invalid clear → account B cache has no A', () async {
      await AuthService.setTokens(
        accessToken: 'a-token',
        refreshToken: 'a-refresh',
      );
      UserIdentityService.debugSetCachedUserId(111);
      await UserProfileManager.saveProfile(
        UserProfile(
          userId: 111,
          phoneNumber: '+989111111111',
          isVerified: true,
        ),
      );

      await SessionGateResolver.resolveColdStart(
        profileService: _FakeAuthProfileService([_unauthorized()]),
        tryRefresh: () async => false,
      );
      expect(UserIdentityService.debugCachedUserId(), isNull);

      await AuthService.setTokens(
        accessToken: 'b-token',
        refreshToken: 'b-refresh',
      );
      await AuthProfileService().cacheProfileFromBackend(_me(222));
      expect(UserIdentityService.debugCachedUserId(), 222);
      expect(UserIdentityService.debugCachedUserId(), isNot(111));
    });
  });

  group('R1 logout health subject reset', () {
    test('clearSessionState drops prior subjects', () {
      final c = SediHealthSubjectController.instance;
      c.debugSeedForTest(subjects: [
        const SediHealthSubject(
          id: 1,
          displayName: 'Me',
          subjectKind: 'self',
          status: 'active',
          accessRole: 'SELF',
        ),
        const SediHealthSubject(
          id: 9,
          displayName: 'Other',
          subjectKind: 'managed',
          status: 'active',
          accessRole: 'MANAGER',
        ),
      ]);
      expect(c.activeSubject?.id, 1);

      c.clearSessionState();
      UserIdentityService.clearCache();

      expect(c.accessibleSubjects, isEmpty);
      expect(c.selfSubject, isNull);
      expect(c.activeSubject, isNull);
      expect(UserIdentityService.debugCachedUserId(), isNull);
    });

    test('AuthHelper logout path clears identity and subjects', () {
      final helper = _readLib('core/auth/auth_helper.dart');
      expect(helper.contains('UserIdentityService.clearCache()'), isTrue);
      expect(
        helper.contains(
            'SediHealthSubjectController.instance.clearSessionState()'),
        isTrue,
      );
    });
  });

  group('R1 Gate3 empty state', () {
    test('sampleIntro dialogue removed; non-clinical empty hint present', () {
      final page = _readLib(
        'features/gate3_interactive/presentation/pages/gate3_interactive_page.dart',
      );
      final l10nSrc = _readLib(
        'features/gate3_interactive/presentation/gate3_localization.dart',
      );

      expect(page.contains('sampleIntro'), isFalse);
      expect(page.contains('_sampleMessages'), isFalse);
      expect(l10nSrc.contains('sampleIntroAssistant'), isFalse);
      expect(l10nSrc.contains('Share your symptoms'), isFalse);
      expect(page.contains('emptyConversationHint'), isTrue);
      expect(page.contains('MessageBubble'), isTrue);

      const l10n = Gate3Localization('en');
      expect(l10n.emptyConversationHint, 'Your conversation will appear here.');
      expect(l10n.emptyConversationHint.toLowerCase().contains('symptom'),
          isFalse);
      expect(
        l10n.emptyConversationHint.toLowerCase().contains('feeling'),
        isFalse,
      );
    });
  });
}
