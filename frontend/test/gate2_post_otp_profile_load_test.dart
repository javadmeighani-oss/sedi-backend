import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/network/api_response.dart';
import 'package:sedi_app/data/dto/auth/me_profile.dart';
import 'package:sedi_app/data/dto/auth/me_profile_parser.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_post_otp_router.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_profile_rules.dart';

void main() {
  group('ApiResponse envelope parsing', () {
    test('parses string ok true for /auth/me', () {
      final response = ApiResponse.fromJson<MeProfileDto>(
        {
          'ok': 'true',
          'data': {
            'user_id': 7,
            'phone': '+989121234567',
          },
          'error': null,
        },
        parseMeProfileDto,
      );

      expect(response.ok, isTrue);
      expect(response.data?.userId, 7);
    });

    test('treats HTTP-style data-only payload as success', () {
      final response = ApiResponse.fromJson<MeProfileDto>(
        {
          'data': {
            'user_id': 9,
            'phone': '+989121234567',
          },
        },
        parseMeProfileDto,
      );

      expect(response.ok, isTrue);
      expect(response.data?.userId, 9);
    });
  });

  group('MeProfileDto parsing', () {
    test('accepts missing optional profile fields', () {
      final profile = MeProfileDto.fromJson({
        'user_id': 12,
        'phone': '+989121234567',
      });

      expect(profile.userId, 12);
      expect(profile.name, isNull);
      expect(Gate2ProfileRules.isProfileComplete(profile), isFalse);
    });

    test('accepts numeric birth fields encoded as doubles', () {
      final profile = MeProfileDto.fromJson({
        'user_id': 12,
        'phone': '+989121234567',
        'name': 'Sara',
        'sex': 'female',
        'calendar_type': 'jalali',
        'birth_day': 15.0,
        'birth_month': 3.0,
        'birth_year': 1370.0,
        'date_of_birth': '1991-04-04',
      });

      expect(profile.birthDay, 15);
      expect(profile.birthMonth, 3);
      expect(profile.birthYear, 1370);
      expect(Gate2ProfileRules.isProfileComplete(profile), isTrue);
    });
  });

  group('Gate2PostOtpRouter incomplete profile', () {
    test('does not require complete profile for routing decision input', () {
      const incomplete = MeProfileDto(
        userId: 42,
        phone: '+989121234567',
      );

      final action = Gate2PostOtpRouter.decide(
        isNewUserPath: false,
        me: incomplete,
        registrationDraftComplete: false,
      );

      expect(action, Gate2PostOtpAction.showProfileCorrectionReturning);
      expect(Gate2ProfileRules.isProfileComplete(incomplete), isFalse);
    });

    test('complete profile routes to Gate 3 without PATCH', () {
      const complete = MeProfileDto(
        userId: 42,
        phone: '+989121234567',
        name: 'Sara',
        sex: 'female',
        calendarType: 'jalali',
        birthDay: 1,
        birthMonth: 1,
        birthYear: 1370,
      );

      final action = Gate2PostOtpRouter.decide(
        isNewUserPath: false,
        me: complete,
        registrationDraftComplete: false,
      );

      expect(action, Gate2PostOtpAction.enterGate3);
    });
  });
}
