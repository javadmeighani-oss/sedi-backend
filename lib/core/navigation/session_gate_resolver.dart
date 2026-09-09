import '../../data/models/user_profile.dart';

import '../auth/auth_service.dart';

import '../auth/auth_profile_service.dart';

import '../utils/user_profile_manager.dart';

import 'app_gate.dart';



/// Single decision point: which gate should open after splash (Gate 1).

class SessionGateResolver {

  SessionGateResolver._();



  /// Returns Gate 3 when a persisted session is valid; otherwise Gate 2.

  static Future<SediAppGate> resolveAfterSplash() async {

    final valid = await hasValidSession();

    return valid ? SediAppGate.heart : SediAppGate.login;

  }



  /// Valid session = access token + backend-confirmed profile with user id and phone.

  /// Returning users may omit local name until `/auth/me` recovery completes.

  static Future<bool> hasValidSession() async {

    final hasToken = await AuthService.hasToken();

    if (!hasToken) return false;



    if (_profileMeetsGateRequirements(await UserProfileManager.loadProfile())) {

      return true;

    }



    final me = await AuthProfileService().fetchAndCacheProfile();

    if (!me.ok || me.data == null) return false;



    return _profileMeetsGateRequirements(await UserProfileManager.loadProfile());

  }



  static bool _profileMeetsGateRequirements(UserProfile profile) {

    final hasPhone =

        profile.phoneNumber != null && profile.phoneNumber!.trim().isNotEmpty;

    final hasUserId = profile.userId != null && profile.userId! > 0;

    return hasUserId && profile.isVerified && hasPhone;

  }

}

