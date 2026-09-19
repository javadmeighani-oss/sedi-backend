import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/data/dto/auth/otp_verify_response.dart';
import 'package:sedi_app/data/dto/auth/post_otp_profile_fallback.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_post_otp_router.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_post_otp_safe_router.dart';

void main() {
  group('postOtpProfileFromVerify', () {
    test('builds minimal profile from verify payload', () {
      const verify = OtpVerifyResponse(
        userId: 42,
        phone: '+989121234567',
        accessToken: 'token',
        language: 'fa',
      );

      final profile = postOtpProfileFromVerify(verify);
      expect(profile, isNotNull);
      expect(profile!.userId, 42);
      expect(profile.phone, '+989121234567');
      expect(profile.preferredLanguage, 'fa');
    });

    test('uses fallback phone when verify omits phone', () {
      const verify = OtpVerifyResponse(
        userId: 7,
        accessToken: 'token',
      );

      final profile = postOtpProfileFromVerify(
        verify,
        fallbackPhoneE164: '+989177777777',
      );

      expect(profile?.phone, '+989177777777');
    });

    test('routes new-user flow to registration completion via safe router', () {
      const verify = OtpVerifyResponse(
        userId: 42,
        phone: '+989121234567',
        accessToken: 'token',
      );
      final profile = postOtpProfileFromVerify(verify);
      expect(profile, isNotNull);

      final action = Gate2PostOtpSafeRouter.resolve(
        meSource: PostOtpMeSource.otpFallbackDraft,
        isNewUserPath: true,
        me: profile!,
        registrationDraftComplete: false,
      );
      expect(action, Gate2PostOtpAction.showRegistrationCompletion);
      expect(action, isNot(Gate2PostOtpAction.enterGate3));
    });

    test('returns null without user id or phone', () {
      const verify = OtpVerifyResponse(accessToken: 'token');
      expect(postOtpProfileFromVerify(verify), isNull);
      expect(
        postOtpProfileFromVerify(
          const OtpVerifyResponse(userId: 1),
          fallbackPhoneE164: '',
        ),
        isNull,
      );
    });
  });
}
