import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/auth/auth_profile_service.dart';
import 'package:sedi_app/core/auth/auth_service.dart';
import 'package:sedi_app/core/navigation/app_gate.dart';
import 'package:sedi_app/core/navigation/session_gate_resolver.dart';
import 'package:sedi_app/core/network/api_error.dart';
import 'package:sedi_app/core/network/api_response.dart';
import 'package:sedi_app/core/utils/user_profile_manager.dart';
import 'package:sedi_app/data/dto/auth/me_profile.dart';
import 'package:sedi_app/data/models/user_profile.dart';
import 'package:sedi_app/features/intro/presentation/pages/intro_page.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _FakeAuthProfileService extends AuthProfileService {
  _FakeAuthProfileService(this._responses);

  final List<ApiResponse<MeProfileDto>> _responses;
  int fetchCount = 0;
  int cacheCount = 0;

  @override
  Future<ApiResponse<MeProfileDto>> fetchMe({
    String? accessToken,
    bool recoverSessionOn401 = true,
  }) async {
    final idx = fetchCount.clamp(0, _responses.length - 1);
    fetchCount++;
    return _responses[idx];
  }

  @override
  Future<void> cacheProfileFromBackend(MeProfileDto me) async {
    cacheCount++;
    await super.cacheProfileFromBackend(me);
  }
}

MeProfileDto _okMe() => MeProfileDto(
      userId: 42,
      phone: '+989121234567',
      name: 'Sara',
      preferredLanguage: 'fa',
    );

ApiResponse<MeProfileDto> _ok() => ApiResponse<MeProfileDto>(
      ok: true,
      data: _okMe(),
      statusCode: 200,
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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
    AuthService.resetForTest();
    await AuthService.clearUserData();
    await UserProfileManager.clearProfile();
  });

  group('A1 session authority', () {
    test('no-session → A2', () async {
      final result = await SessionGateResolver.resolveColdStart(
        profileService: _FakeAuthProfileService([_ok()]),
      );
      expect(result.status, SessionResolveStatus.noSession);
      expect(result.nextGate, SediAppGate.login);
    });

    test('local profile alone cannot authorize A3', () async {
      await AuthService.setTokens(
        accessToken: 'stale-access',
        refreshToken: 'stale-refresh',
      );
      await UserProfileManager.saveProfile(
        UserProfile(
          name: 'Sara',
          phoneNumber: '+989121234567',
          userId: 42,
          isVerified: true,
          preferredLanguage: 'fa',
        ),
      );

      // Backend rejects — local profile must not short-circuit to A3.
      final fake = _FakeAuthProfileService([_unauthorized()]);
      final result = await SessionGateResolver.resolveColdStart(
        profileService: fake,
        tryRefresh: () async => false,
      );

      expect(fake.fetchCount, greaterThanOrEqualTo(1));
      expect(result.nextGate, SediAppGate.login);
      expect(result.status, SessionResolveStatus.authInvalid);
      expect(await AuthService.hasToken(), isFalse);
    });

    test('valid stored session + /auth/me success → A3', () async {
      await AuthService.setTokens(
        accessToken: 'access',
        refreshToken: 'refresh',
      );
      final fake = _FakeAuthProfileService([_ok()]);
      final result = await SessionGateResolver.resolveColdStart(
        profileService: fake,
      );

      expect(result.status, SessionResolveStatus.authenticated);
      expect(result.nextGate, SediAppGate.heart);
      expect(fake.cacheCount, 1);
    });

    test('/auth/me 401 + refresh success → A3', () async {
      await AuthService.setTokens(
        accessToken: 'expired',
        refreshToken: 'refresh',
      );
      final fake = _FakeAuthProfileService([_unauthorized(), _ok()]);
      final result = await SessionGateResolver.resolveColdStart(
        profileService: fake,
        tryRefresh: () async {
          await AuthService.setTokens(
            accessToken: 'new-access',
            refreshToken: 'new-refresh',
          );
          return true;
        },
      );

      expect(fake.fetchCount, 2);
      expect(result.status, SessionResolveStatus.authenticated);
      expect(result.nextGate, SediAppGate.heart);
    });

    test('/auth/me 401 + refresh fail → A2', () async {
      await AuthService.setTokens(
        accessToken: 'expired',
        refreshToken: 'bad-refresh',
      );
      final fake = _FakeAuthProfileService([_unauthorized()]);
      final result = await SessionGateResolver.resolveColdStart(
        profileService: fake,
        tryRefresh: () async => false,
      );

      expect(result.status, SessionResolveStatus.authInvalid);
      expect(result.nextGate, SediAppGate.login);
      expect(await AuthService.hasToken(), isFalse);
    });

    test('backend unavailable keeps tokens and routes A2', () async {
      await AuthService.setTokens(
        accessToken: 'access',
        refreshToken: 'refresh',
      );
      final fake = _FakeAuthProfileService([_network()]);
      final result = await SessionGateResolver.resolveColdStart(
        profileService: fake,
      );

      expect(result.status, SessionResolveStatus.backendUnavailable);
      expect(result.nextGate, SediAppGate.login);
      expect(await AuthService.hasToken(), isTrue);
    });
  });

  group('A1 intro', () {
    testWidgets('IntroPage appears on app open', (tester) async {
      await tester.pumpWidget(const MaterialApp(home: IntroPage()));
      expect(find.byType(IntroPage), findsOneWidget);
      expect(find.byType(Image), findsWidgets);
      // Advance partially through the 2.5s birth animation.
      await tester.pump(const Duration(milliseconds: 800));
      expect(find.byType(IntroPage), findsOneWidget);
      // Flush remaining intro / health timers before dispose.
      await tester.pump(const Duration(milliseconds: 3500));
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();
    });
  });
}
