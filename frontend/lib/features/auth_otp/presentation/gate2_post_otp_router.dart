import '../../../data/dto/auth/me_profile.dart';
import 'gate2_profile_rules.dart';

/// Actions after OTP verification once the auth token is stored.
enum Gate2PostOtpAction {
  enterGate3,
  showProfileCorrectionReturning,
  showProfileCorrectionAlreadyRegistered,
  patchRegistrationThenEnterGate3,
  showRegistrationCompletion,
}

/// Pure routing rules for post-OTP profile sync and Gate 3 entry.
class Gate2PostOtpRouter {
  Gate2PostOtpRouter._();

  static Gate2PostOtpAction decide({
    required bool isNewUserPath,
    required MeProfileDto me,
    required bool registrationDraftComplete,
  }) {
    final profileComplete = Gate2ProfileRules.isProfileComplete(me);

    if (isNewUserPath) {
      if (profileComplete) {
        return Gate2PostOtpAction.showProfileCorrectionAlreadyRegistered;
      }
      if (registrationDraftComplete) {
        return Gate2PostOtpAction.patchRegistrationThenEnterGate3;
      }
      return Gate2PostOtpAction.showRegistrationCompletion;
    }

    if (profileComplete) {
      return Gate2PostOtpAction.enterGate3;
    }
    return Gate2PostOtpAction.showProfileCorrectionReturning;
  }
}

/// Registration draft completeness without relying on mounted Form widgets.
class Gate2RegistrationDraft {
  final String name;
  final String? gender;
  final int? birthDay;
  final int? birthMonth;
  final int? birthYear;
  final String requestedPhone;
  final bool phoneVerifiedInSession;

  const Gate2RegistrationDraft({
    required this.name,
    required this.gender,
    required this.birthDay,
    required this.birthMonth,
    required this.birthYear,
    required this.requestedPhone,
    required this.phoneVerifiedInSession,
  });

  bool get hasCompleteDob =>
      birthDay != null && birthMonth != null && birthYear != null;

  bool get isComplete =>
      phoneVerifiedInSession &&
      name.trim().isNotEmpty &&
      gender != null &&
      gender!.isNotEmpty &&
      hasCompleteDob &&
      requestedPhone.isNotEmpty;
}
