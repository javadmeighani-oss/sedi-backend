import 'dart:io';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/auth/auth_profile_service.dart';
import 'package:sedi_app/core/auth/auth_refresh_service.dart';
import 'package:sedi_app/core/auth/auth_service.dart';
import 'package:sedi_app/core/auth/user_identity_service.dart';
import 'package:sedi_app/core/navigation/app_gate.dart';
import 'package:sedi_app/core/navigation/session_gate_resolver.dart';
import 'package:sedi_app/core/network/api_error.dart';
import 'package:sedi_app/core/network/api_response.dart';
import 'package:sedi_app/core/utils/user_profile_manager.dart';
import 'package:sedi_app/data/dto/auth/me_profile.dart';
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

MeProfileDto _okMe() => const MeProfileDto(
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
    UserIdentityService.clearCache();
  });

  test('transient => tokens preserved, no A2/Login', () async {
    await AuthService.setTokens(
      accessToken: 'access',
      refreshToken: 'refresh',
    );
    final result = await SessionGateResolver.resolveColdStart(
      profileService: _FakeAuthProfileService([_network()]),
    );
    expect(result.status, SessionResolveStatus.backendUnavailable);
    expect(result.stayOnStartup, isTrue);
    expect(result.nextGate, SediAppGate.splash);
    expect(result.nextGate, isNot(SediAppGate.login));
    expect(result.nextGate, isNot(SediAppGate.heart));
    expect(await AuthService.hasToken(), isTrue);

    final refreshTransient = await SessionGateResolver.resolveColdStart(
      profileService: _FakeAuthProfileService([_unauthorized()]),
      refreshOnce: () async => AuthRefreshOutcome.transientFailure,
    );
    expect(refreshTransient.stayOnStartup, isTrue);
    expect(refreshTransient.nextGate, isNot(SediAppGate.login));
    expect(await AuthService.hasToken(), isTrue);
  });

  test('recovered backend => A3 after revalidation', () async {
    await AuthService.setTokens(
      accessToken: 'access',
      refreshToken: 'refresh',
    );
    final fake = _FakeAuthProfileService([_network(), _ok()]);
    final first = await SessionGateResolver.resolveColdStart(
      profileService: fake,
    );
    expect(first.stayOnStartup, isTrue);
    expect(first.nextGate, isNot(SediAppGate.heart));
    expect(await AuthService.hasToken(), isTrue);

    final recovered = await SessionGateResolver.resolveColdStart(
      profileService: fake,
    );
    expect(recovered.status, SessionResolveStatus.authenticated);
    expect(recovered.nextGate, SediAppGate.heart);
    expect(await AuthService.hasToken(), isTrue);
  });

  test('invalid refresh => A2/Login + session clear', () async {
    await AuthService.setTokens(
      accessToken: 'expired',
      refreshToken: 'bad-refresh',
    );
    UserIdentityService.debugSetCachedUserId(99);
    final result = await SessionGateResolver.resolveColdStart(
      profileService: _FakeAuthProfileService([_unauthorized()]),
      tryRefresh: () async => false,
    );
    expect(result.status, SessionResolveStatus.authInvalid);
    expect(result.nextGate, SediAppGate.login);
    expect(result.stayOnStartup, isFalse);
    expect(await AuthService.hasToken(), isFalse);
    expect(UserIdentityService.debugCachedUserId(), isNull);
  });

  test('Intro retries stayOnStartup and never routes splash to Login', () {
    final intro = File(
      'lib/features/intro/presentation/pages/intro_page.dart',
    ).readAsStringSync();
    expect(intro.contains('while (session.stayOnStartup)'), isTrue);
    expect(intro.contains('kReconnectRetryDelay'), isTrue);
    expect(intro.contains('session.nextGate == SediAppGate.splash'), isTrue);
    expect(intro.contains('resolveColdStart()'), isTrue);
  });
}
