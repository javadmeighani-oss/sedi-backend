import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/auth/auth_profile_service.dart';
import 'package:sedi_app/core/network/api_response.dart';
import 'package:sedi_app/data/dto/auth/auth_me_response_parser.dart';
import 'package:sedi_app/data/dto/auth/me_profile.dart';
import 'package:sedi_app/data/dto/auth/me_profile_parser.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_post_otp_router.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_profile_rules.dart';

import 'fixtures/auth_me_backend_fixture.dart';

void main() {
  group('A. ApiResponse flat data envelope', () {
    test('parses top-level ok/data/error with flat profile data', () {
      final response = ApiResponse.fromJson<MeProfileDto>(
        backendAuthMeEnvelope(backendAuthMeIncompleteProfile),
        parseMeProfileDto,
      );

      expect(response.ok, isTrue);
      expect(response.data?.userId, 42);
      expect(response.error, isNull);
    });
  });

  group('B. Backend MeOut schema fidelity', () {
    test('parses exact backend incomplete profile fixture', () {
      final response = ApiResponse.fromJson<MeProfileDto>(
        backendAuthMeEnvelope(backendAuthMeIncompleteProfile),
        parseMeProfileDto,
      );

      expect(response.ok, isTrue);
      expect(response.data?.userId, 42);
      expect(response.data?.phone, '+989121234567');
      expect(response.data?.preferredLanguage, 'fa');
      expect(response.data?.name, isNull);
      expect(response.data?.sex, isNull);
      expect(response.data?.dateOfBirth, isNull);
    });

    test('parses exact backend complete profile fixture', () {
      final profile = parseMeProfileDto(backendAuthMeCompleteProfile);

      expect(profile, isNotNull);
      expect(profile!.birthDay, 1);
      expect(profile.birthMonth, 1);
      expect(profile.birthYear, 1370);
      expect(profile.dateOfBirth, '1991-04-04');
      expect(Gate2ProfileRules.isProfileComplete(profile), isTrue);
    });
  });

  group('C. Missing optional fields', () {
    test('parses successfully and routes to profile completion', () {
      final profile = parseMeProfileDto(backendAuthMeIncompleteProfile);

      expect(profile, isNotNull);
      expect(Gate2ProfileRules.isProfileComplete(profile!), isFalse);

      final action = Gate2PostOtpRouter.decide(
        isNewUserPath: true,
        me: profile,
        registrationDraftComplete: false,
      );

      expect(action, Gate2PostOtpAction.showRegistrationCompletion);
    });
  });

  group('D. user_id as int', () {
    test('parses safely', () {
      final profile = parseMeProfileDto({
        'user_id': 99,
        'phone': '+989121234567',
      });

      expect(profile?.userId, 99);
    });
  });

  group('E. user_id as string', () {
    test('parses safely', () {
      final profile = parseMeProfileDto({
        'user_id': '99',
        'phone': '+989121234567',
      });

      expect(profile?.userId, 99);
    });
  });

  group('F. birth fields as int/double/string', () {
    test('parses int, double, and string birth fields', () {
      final profile = parseMeProfileDto({
        'user_id': 12,
        'phone': '+989121234567',
        'birth_day': 15.0,
        'birth_month': '3',
        'birth_year': 1370,
      });

      expect(profile?.birthDay, 15);
      expect(profile?.birthMonth, 3);
      expect(profile?.birthYear, 1370);
    });
  });

  group('G. date_of_birth null', () {
    test('does not fail parsing', () {
      final profile = parseMeProfileDto({
        'user_id': 12,
        'phone': '+989121234567',
        'date_of_birth': null,
      });

      expect(profile, isNotNull);
      expect(profile?.dateOfBirth, isNull);
    });
  });

  group('H. complete profile after OTP cache path', () {
    test('complete profile is cacheable and routes to Gate 3', () async {
      final profile = parseMeProfileDto(backendAuthMeCompleteProfile);
      expect(profile, isNotNull);
      expect(Gate2ProfileRules.isProfileComplete(profile!), isTrue);

      final action = Gate2PostOtpRouter.decide(
        isNewUserPath: false,
        me: profile,
        registrationDraftComplete: false,
      );
      expect(action, Gate2PostOtpAction.enterGate3);

      final userProfile = AuthProfileService.toUserProfile(profile);
      expect(userProfile.userId, 42);
      expect(userProfile.isVerified, isTrue);
    });
  });

  group('I. incomplete profile after OTP', () {
    test('routes to completion/correction instead of parse failure', () {
      final profile = parseMeProfileDto(backendAuthMeIncompleteProfile);
      expect(profile, isNotNull);

      final returningAction = Gate2PostOtpRouter.decide(
        isNewUserPath: false,
        me: profile!,
        registrationDraftComplete: false,
      );
      expect(returningAction, Gate2PostOtpAction.showProfileCorrectionReturning);

      final newUserAction = Gate2PostOtpRouter.decide(
        isNewUserPath: true,
        me: profile,
        registrationDraftComplete: false,
      );
      expect(newUserAction, Gate2PostOtpAction.showRegistrationCompletion);
    });
  });

  group('J. malformed required identity fields', () {
    test('missing user_id fails parse', () {
      expect(
        parseMeProfileDto({'phone': '+989121234567'}),
        isNull,
      );
    });

    test('missing phone fails parse', () {
      expect(
        parseMeProfileDto({'user_id': 42}),
        isNull,
      );
    });

    test('envelope ok:true with unparseable data reports PARSE_ERROR', () {
      final response = ApiResponse.fromJson<MeProfileDto>(
        {
          'ok': true,
          'data': 'not-a-profile-map',
          'error': null,
        },
        parseMeProfileDto,
      );

      expect(response.ok, isFalse);
      expect(response.data, isNull);
      expect(response.error?.code, 'PARSE_ERROR');
    });
  });

  group('Envelope edge cases', () {
    test('parses flat identity fields when data key is absent', () {
      final result = AuthMeResponseParser.parseHttpResponse(
        statusCode: 200,
        body: '{"ok":true,"error":null,"user_id":42,"phone":"+989121234567","preferred_language":"fa"}',
        knownPhoneE164: '+989121234567',
      );

      expect(result.ok, isTrue);
      expect(result.profile?.userId, 42);
    });

    test('parses JSON string data payload', () {
      final response = ApiResponse.fromJson<MeProfileDto>(
        {
          'ok': true,
          'data':
              '{"user_id":42,"phone":"+989121234567","preferred_language":"fa"}',
          'error': null,
        },
        parseMeProfileDto,
      );

      expect(response.ok, isTrue);
      expect(response.data?.userId, 42);
    });

    test('parses nested data.profile shape when present', () {
      final response = ApiResponse.fromJson<MeProfileDto>(
        {
          'ok': true,
          'data': {
            'profile': backendAuthMeIncompleteProfile,
          },
          'error': null,
        },
        parseMeProfileDto,
      );

      expect(response.ok, isTrue);
      expect(response.data?.userId, 42);
    });

    test('dedicated parser unwraps nested data.user shape', () {
      final result = AuthMeResponseParser.parseHttpResponse(
        statusCode: 200,
        body: '{"ok":true,"data":{"user":{"user_id":42,"phone":"+989121234567"}},"error":null}',
        knownPhoneE164: '+989121234567',
      );

      expect(result.ok, isTrue);
      expect(result.profile?.userId, 42);
      expect(result.profile?.phone, '+989121234567');
    });
  });
}
