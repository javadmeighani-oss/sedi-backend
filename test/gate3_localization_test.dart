import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/gate3_localization.dart';

void main() {
  test('Gate3Localization fa keeps exact composer placeholder', () {
    const l10n = Gate3Localization('fa');
    expect(l10n.composerPlaceholder, 'صحبت با صدی');
    expect(l10n.camera, 'دوربین');
    expect(l10n.photos, 'تصاویر');
    expect(l10n.files, 'فایل‌ها');
    expect(l10n.isRtl, isTrue);
  });

  test('Gate3Localization en is LTR with localized labels', () {
    const l10n = Gate3Localization('en');
    expect(l10n.isRtl, isFalse);
    expect(l10n.settings, 'Settings');
    expect(l10n.healthCare, 'Health Care');
    expect(l10n.composerPlaceholder, 'Talk to Sedi');
  });

  test('Gate3Localization ar provides RTL labels', () {
    const l10n = Gate3Localization('ar');
    expect(l10n.isRtl, isTrue);
    expect(l10n.gadgets, 'الأجهزة');
  });
}
