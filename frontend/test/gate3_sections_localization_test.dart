import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/gate3_interactive/logic/gate3_phone_utils.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/gate3_sections_localization.dart';

void main() {
  group('Gate3SectionsLocalization', () {
    test('fa titles and RTL', () {
      const l10n = Gate3SectionsLocalization('fa');
      expect(l10n.isRtl, isTrue);
      expect(l10n.settingsTitle, 'تنظیمات');
      expect(l10n.closeContactsTitle, 'تماس با نزدیکان');
      expect(l10n.healthCareTitle, 'مراقبت سلامت');
      expect(l10n.lifestyleTitle, 'سبک زندگی');
      expect(l10n.gadgetsTitle, 'گجت‌ها');
    });

    test('en titles and LTR', () {
      const l10n = Gate3SectionsLocalization('en');
      expect(l10n.isRtl, isFalse);
      expect(l10n.settingsTitle, 'Settings');
      expect(l10n.closeContactsTitle, 'Close contacts');
    });

    test('ar close contacts title', () {
      const l10n = Gate3SectionsLocalization('ar');
      expect(l10n.isRtl, isTrue);
      expect(l10n.closeContactsTitle, 'جهات الاتصال المقربة');
    });

    test('empty state strings exist', () {
      const l10n = Gate3SectionsLocalization('en');
      expect(l10n.noContactsTitle, isNotEmpty);
      expect(l10n.noRecentData, isNotEmpty);
      expect(l10n.noHubRegistered, isNotEmpty);
    });
  });

  group('Gate3PhoneUtils', () {
    test('invalid phone fails validation', () {
      expect(Gate3PhoneUtils.isValid('12'), isFalse);
    });

    test('normalized iranian mobile is valid', () {
      expect(Gate3PhoneUtils.isValid('09123456789'), isTrue);
      expect(Gate3PhoneUtils.normalize('09123456789'), '+989123456789');
    });
  });
}
