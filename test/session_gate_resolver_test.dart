import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/auth/auth_service.dart';
import 'package:sedi_app/core/navigation/app_gate.dart';
import 'package:sedi_app/core/navigation/session_gate_resolver.dart';
import 'package:sedi_app/core/utils/user_profile_manager.dart';
import 'package:sedi_app/data/models/user_profile.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await AuthService.clearUserData();
    await UserProfileManager.clearProfile();
  });

  test('resolveAfterSplash returns login when no session', () async {
    final gate = await SessionGateResolver.resolveAfterSplash();
    expect(gate, SediAppGate.login);
  });

  test('resolveAfterSplash returns heart when session is complete', () async {
    await AuthService.setTokens(
      accessToken: 'test-access-token',
      refreshToken: 'test-refresh-token',
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

    final gate = await SessionGateResolver.resolveAfterSplash();
    expect(gate, SediAppGate.heart);
  });

  test('hasValidSession is false without access token', () async {
    await UserProfileManager.saveProfile(
      UserProfile(
        name: 'Sara',
        phoneNumber: '+989121234567',
        userId: 42,
        isVerified: true,
      ),
    );

    expect(await SessionGateResolver.hasValidSession(), isFalse);
  });
}
