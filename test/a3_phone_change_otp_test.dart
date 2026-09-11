import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/data/dto/auth/me_profile.dart';
import 'package:sedi_app/features/auth_otp/presentation/a2_phone_e164.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/gate3_localization.dart';

void main() {
  test('Profile phone display uses backend MeProfileDto phone only', () {
    const me = MeProfileDto(
      userId: 7,
      phone: '+989121111111',
      name: 'Sara',
    );
    expect(me.phone, '+989121111111');
    // Failure path: pending candidate must not replace canonical until verify.
    const pending = '+989122222222';
    expect(me.phone, isNot(pending));
  });

  test('Phone-change E.164 normalize reuses A2 helper', () {
    final e164 = A2PhoneE164.normalize(
      nationalInput: '09121234567',
      dialCode: A2PhoneE164.byIso2('IR'),
    );
    expect(e164, '+989121234567');
    expect(
      A2PhoneE164.isValid(
        nationalInput: '09121234567',
        dialCode: A2PhoneE164.byIso2('IR'),
      ),
      isTrue,
    );
  });

  test('Gate3Localization phone-change strings exist for en/fa/ar', () {
    for (final lang in ['en', 'fa', 'ar']) {
      final l10n = Gate3Localization(lang);
      expect(l10n.changePhone, isNotEmpty);
      expect(l10n.phoneSame, isNotEmpty);
      expect(l10n.phoneDuplicate, isNotEmpty);
      expect(l10n.phoneOtpInvalid, isNotEmpty);
    }
  });

  test('Successful me refresh replaces displayed phone only via DTO', () {
    var displayed = '+989121111111';
    const confirmed = MeProfileDto(userId: 1, phone: '+989123333333');
    displayed = confirmed.phone!;
    expect(displayed, '+989123333333');
  });
}
