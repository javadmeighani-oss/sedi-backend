import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/network/api_error.dart';
import 'package:sedi_app/core/network/api_response.dart';
import 'package:sedi_app/data/dto/auth/me_profile.dart';
import 'package:sedi_app/data/dto/auth/otp_verify_response.dart';
import 'package:sedi_app/data/dto/auth/post_otp_profile_fallback.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_post_otp_me_failure.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_post_otp_router.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_post_otp_safe_router.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_profile_rules.dart';

import 'fixtures/auth_me_backend_fixture.dart';

void main() {
  const completeMe = MeProfileDto(
    userId: 42,
    phone: '+989121234567',
    name: 'Sara',
    sex: 'female',
    calendarType: 'jalali',
    birthDay: 1,
    birthMonth: 1,
    birthYear: 1370,
  );

  const incompleteMe = MeProfileDto(
    userId: 42,
    phone: '+989121234567',
  );

  group('Gate2PostOtpSafeRouter backend-confirmed', () {
    test('returning complete profile enters Gate 3', () {
      final action = Gate2PostOtpSafeRouter.resolve(
        meSource: PostOtpMeSource.backendConfirmed,
        isNewUserPath: false,
        me: completeMe,
        registrationDraftComplete: false,
      );
      expect(action, Gate2PostOtpAction.enterGate3);
      expect(
        Gate2PostOtpSafeRouter.requiresBackendConfirmedProfile(action),
        isTrue,
      );
    });

    test('returning incomplete profile routes to correction', () {
      final action = Gate2PostOtpSafeRouter.resolve(
        meSource: PostOtpMeSource.backendConfirmed,
        isNewUserPath: false,
        me: incompleteMe,
        registrationDraftComplete: false,
      );
      expect(action, Gate2PostOtpAction.showProfileCorrectionReturning);
    });

    test('new user complete draft PATCHes then requires GET before Gate 3', () {
      final action = Gate2PostOtpSafeRouter.resolve(
        meSource: PostOtpMeSource.backendConfirmed,
        isNewUserPath: true,
        me: incompleteMe,
        registrationDraftComplete: true,
      );
      expect(action, Gate2PostOtpAction.patchRegistrationThenEnterGate3);
      expect(
        Gate2PostOtpSafeRouter.requiresBackendConfirmedProfile(action),
        isFalse,
      );
    });
  });

  group('Gate2PostOtpSafeRouter OTP fallback draft', () {
    test('never enters Gate 3 even when profile looks complete', () {
      final action = Gate2PostOtpSafeRouter.resolve(
        meSource: PostOtpMeSource.otpFallbackDraft,
        isNewUserPath: false,
        me: completeMe,
        registrationDraftComplete: false,
      );
      expect(action, Gate2PostOtpAction.showProfileCorrectionReturning);
      expect(action, isNot(Gate2PostOtpAction.enterGate3));
    });

    test('never uses already-registered correction without backend GET', () {
      final action = Gate2PostOtpSafeRouter.resolve(
        meSource: PostOtpMeSource.otpFallbackDraft,
        isNewUserPath: true,
        me: completeMe,
        registrationDraftComplete: false,
      );
      expect(action, Gate2PostOtpAction.showRegistrationCompletion);
      expect(
        Gate2PostOtpSafeRouter.requiresBackendConfirmedProfile(action),
        isFalse,
      );
    });

    test('incomplete draft routes to registration completion only', () {
      const verify = OtpVerifyResponse(
        userId: 42,
        phone: '+989121234567',
        accessToken: 'token',
      );
      final draft = postOtpProfileFromVerify(verify);
      expect(draft, isNotNull);
      expect(Gate2ProfileRules.isProfileComplete(draft!), isFalse);

      final action = Gate2PostOtpSafeRouter.resolve(
        meSource: PostOtpMeSource.otpFallbackDraft,
        isNewUserPath: true,
        me: draft,
        registrationDraftComplete: false,
      );
      expect(action, Gate2PostOtpAction.showRegistrationCompletion);
    });

    test('complete draft allows PATCH path but not direct Gate 3', () {
      final action = Gate2PostOtpSafeRouter.resolve(
        meSource: PostOtpMeSource.otpFallbackDraft,
        isNewUserPath: true,
        me: incompleteMe,
        registrationDraftComplete: true,
      );
      expect(action, Gate2PostOtpAction.patchRegistrationThenEnterGate3);
      expect(action, isNot(Gate2PostOtpAction.enterGate3));
    });

    test('incomplete draft never PATCHes', () {
      final action = Gate2PostOtpSafeRouter.resolve(
        meSource: PostOtpMeSource.otpFallbackDraft,
        isNewUserPath: true,
        me: incompleteMe,
        registrationDraftComplete: false,
      );
      expect(action, Gate2PostOtpAction.showRegistrationCompletion);
      expect(action, isNot(Gate2PostOtpAction.patchRegistrationThenEnterGate3));
    });
  });

  group('Post-OTP failure classification', () {
    test('401/403 are auth failures and must not use fallback', () {
      for (final status in [401, 403]) {
        final meRes = ApiResponse<MeProfileDto>(
          ok: false,
          error: ApiError(code: 'AUTH_ERROR', message: 'Authentication failed'),
          statusCode: status,
        );
        expect(classifyPostOtpMeFailure(meRes), PostOtpMeFailureKind.auth);
      }
    });

    test('5xx is transient fetch failure eligible for retry', () {
      final meRes = ApiResponse<MeProfileDto>(
        ok: false,
        error: ApiError(code: 'HTTP_503', message: 'Server busy'),
        statusCode: 503,
      );
      expect(classifyPostOtpMeFailure(meRes), PostOtpMeFailureKind.fetch);
      expect(isTransientPostOtpMeFailure(meRes), isTrue);
    });

    test('network failure is transient', () {
      final meRes = ApiResponse<MeProfileDto>(
        ok: false,
        error: ApiError(code: 'NETWORK_ERROR', message: 'SocketException'),
      );
      expect(isTransientPostOtpMeFailure(meRes), isTrue);
    });
  });

  group('Backend fixture routing', () {
    test('incomplete backend profile routes to completion for new user', () {
      final profile = MeProfileDto.fromJson(backendAuthMeIncompleteProfile);
      final action = Gate2PostOtpSafeRouter.resolve(
        meSource: PostOtpMeSource.backendConfirmed,
        isNewUserPath: true,
        me: profile,
        registrationDraftComplete: false,
      );
      expect(action, Gate2PostOtpAction.showRegistrationCompletion);
    });

    test('complete backend profile routes to Gate 3 for returning user', () {
      final profile = MeProfileDto.fromJson(backendAuthMeCompleteProfile);
      expect(Gate2ProfileRules.isProfileComplete(profile), isTrue);

      final action = Gate2PostOtpSafeRouter.resolve(
        meSource: PostOtpMeSource.backendConfirmed,
        isNewUserPath: false,
        me: profile,
        registrationDraftComplete: false,
      );
      expect(action, Gate2PostOtpAction.enterGate3);
    });
  });
}
