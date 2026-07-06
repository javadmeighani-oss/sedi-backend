import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/data/dto/auth/me_profile.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_profile_rules.dart';

void main() {
  group('Gate2ProfileRules.isProfileComplete', () {
    test('returns true when all required fields are present', () {
      const me = MeProfileDto(
        userId: 42,
        phone: '+989121234567',
        name: 'Sara',
        sex: 'female',
        calendarType: 'jalali',
        birthDay: 15,
        birthMonth: 3,
        birthYear: 1370,
      );

      expect(Gate2ProfileRules.isProfileComplete(me), isTrue);
    });

    test('returns false when name is missing', () {
      const me = MeProfileDto(
        userId: 42,
        phone: '+989121234567',
        sex: 'female',
        calendarType: 'jalali',
        birthDay: 15,
        birthMonth: 3,
        birthYear: 1370,
      );

      expect(Gate2ProfileRules.isProfileComplete(me), isFalse);
    });

    test('returns false when birth fields are incomplete', () {
      const me = MeProfileDto(
        userId: 42,
        phone: '+989121234567',
        name: 'Sara',
        sex: 'female',
        calendarType: 'jalali',
        birthDay: 15,
        birthMonth: 3,
      );

      expect(Gate2ProfileRules.isProfileComplete(me), isFalse);
    });

    test('returns false when userId is zero', () {
      const me = MeProfileDto(
        userId: 0,
        phone: '+989121234567',
        name: 'Sara',
        sex: 'female',
        calendarType: 'jalali',
        birthDay: 15,
        birthMonth: 3,
        birthYear: 1370,
      );

      expect(Gate2ProfileRules.isProfileComplete(me), isFalse);
    });
  });
}
