import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/data/dto/auth/me_profile.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_post_otp_router.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_profile_rules.dart';

void main() {
  const completeMe = MeProfileDto(
    userId: 42,
    phone: '+989121234567',
    name: 'Sara',
    sex: 'female',
    calendarType: 'jalali',
    birthDay: 15,
    birthMonth: 3,
    birthYear: 1370,
  );

  const incompleteMe = MeProfileDto(
    userId: 42,
    phone: '+989121234567',
  );

  group('Gate2PostOtpRouter.decide', () {
    test('returning complete user enters Gate 3 without PATCH', () {
      final action = Gate2PostOtpRouter.decide(
        isNewUserPath: false,
        me: completeMe,
        registrationDraftComplete: false,
      );

      expect(action, Gate2PostOtpAction.enterGate3);
      expect(Gate2ProfileRules.isProfileComplete(completeMe), isTrue);
    });

    test('returning incomplete user routes to profile correction', () {
      final action = Gate2PostOtpRouter.decide(
        isNewUserPath: false,
        me: incompleteMe,
        registrationDraftComplete: false,
      );

      expect(action, Gate2PostOtpAction.showProfileCorrectionReturning);
    });

    test('new incomplete user with complete draft PATCHes then enters Gate 3', () {
      final action = Gate2PostOtpRouter.decide(
        isNewUserPath: true,
        me: incompleteMe,
        registrationDraftComplete: true,
      );

      expect(action, Gate2PostOtpAction.patchRegistrationThenEnterGate3);
    });

    test('new incomplete user without draft shows registration completion', () {
      final action = Gate2PostOtpRouter.decide(
        isNewUserPath: true,
        me: incompleteMe,
        registrationDraftComplete: false,
      );

      expect(action, Gate2PostOtpAction.showRegistrationCompletion);
    });

    test('new user with already complete backend profile shows correction', () {
      final action = Gate2PostOtpRouter.decide(
        isNewUserPath: true,
        me: completeMe,
        registrationDraftComplete: true,
      );

      expect(action, Gate2PostOtpAction.showProfileCorrectionAlreadyRegistered);
    });
  });

  group('Gate2RegistrationDraft', () {
    test('isComplete requires verified phone and full registration fields', () {
      const completeDraft = Gate2RegistrationDraft(
        name: 'Sara',
        gender: 'female',
        birthDay: 1,
        birthMonth: 1,
        birthYear: 1370,
        requestedPhone: '+989121234567',
        phoneVerifiedInSession: true,
      );

      const incompleteDraft = Gate2RegistrationDraft(
        name: 'Sara',
        gender: null,
        birthDay: 1,
        birthMonth: 1,
        birthYear: 1370,
        requestedPhone: '+989121234567',
        phoneVerifiedInSession: true,
      );

      expect(completeDraft.isComplete, isTrue);
      expect(incompleteDraft.isComplete, isFalse);
    });
  });
}
