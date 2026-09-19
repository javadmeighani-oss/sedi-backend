import '../../../data/dto/auth/me_profile.dart';
import 'gate2_post_otp_router.dart';
import 'gate2_profile_rules.dart';

/// Whether post-OTP profile data came from a successful GET `/auth/me`.
enum PostOtpMeSource {
  backendConfirmed,
  otpFallbackDraft,
}

/// Gate 2-only routing when `/auth/me` failed and identity comes from OTP verify.
///
/// Fallback may continue registration/correction inside Gate 2 only.
/// It must never enter Gate 3, cache profile, or skip mandatory GET `/auth/me`.
class Gate2PostOtpSafeRouter {
  Gate2PostOtpSafeRouter._();

  static Gate2PostOtpAction resolve({
    required PostOtpMeSource meSource,
    required bool isNewUserPath,
    required MeProfileDto me,
    required bool registrationDraftComplete,
  }) {
    final action = Gate2PostOtpRouter.decide(
      isNewUserPath: isNewUserPath,
      me: me,
      registrationDraftComplete: registrationDraftComplete,
    );

    if (meSource == PostOtpMeSource.backendConfirmed) {
      return action;
    }

    return _restrictFallbackAction(
      action: action,
      isNewUserPath: isNewUserPath,
      registrationDraftComplete: registrationDraftComplete,
    );
  }

  /// True when [action] may write cache or enter Gate 3 (backend GET required).
  static bool requiresBackendConfirmedProfile(Gate2PostOtpAction action) {
    switch (action) {
      case Gate2PostOtpAction.enterGate3:
      case Gate2PostOtpAction.showProfileCorrectionAlreadyRegistered:
        return true;
      case Gate2PostOtpAction.patchRegistrationThenEnterGate3:
      case Gate2PostOtpAction.showProfileCorrectionReturning:
      case Gate2PostOtpAction.showRegistrationCompletion:
        return false;
    }
  }

  static Gate2PostOtpAction _restrictFallbackAction({
    required Gate2PostOtpAction action,
    required bool isNewUserPath,
    required bool registrationDraftComplete,
  }) {
    switch (action) {
      case Gate2PostOtpAction.enterGate3:
        return Gate2PostOtpAction.showProfileCorrectionReturning;
      case Gate2PostOtpAction.showProfileCorrectionAlreadyRegistered:
        return isNewUserPath
            ? Gate2PostOtpAction.showRegistrationCompletion
            : Gate2PostOtpAction.showProfileCorrectionReturning;
      case Gate2PostOtpAction.patchRegistrationThenEnterGate3:
        if (!registrationDraftComplete) {
          return Gate2PostOtpAction.showRegistrationCompletion;
        }
        return Gate2PostOtpAction.patchRegistrationThenEnterGate3;
      case Gate2PostOtpAction.showProfileCorrectionReturning:
      case Gate2PostOtpAction.showRegistrationCompletion:
        return action;
    }
  }

  /// Fallback drafts are identity-only and never backend-complete.
  static bool isFallbackProfileComplete(MeProfileDto me) {
    return Gate2ProfileRules.isProfileComplete(me);
  }
}
