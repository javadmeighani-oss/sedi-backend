import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/gate3_localization.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/sedi_brain_orb.dart';

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
    expect(l10n.readMore, 'قراءة المزيد');
    expect(l10n.showLess, 'عرض أقل');
  });

  test('Gate3Localization expansion labels', () {
    expect(const Gate3Localization('fa').readMore, 'ادامه متن');
    expect(const Gate3Localization('fa').showLess, 'نمایش کمتر');
    expect(const Gate3Localization('en').readMore, 'Read more');
    expect(const Gate3Localization('en').showLess, 'Show less');
    expect(const Gate3Localization('ar').readMore, 'قراءة المزيد');
    expect(const Gate3Localization('ar').showLess, 'عرض أقل');
  });

  test('Gate3Localization fa history labels', () {
    const l10n = Gate3Localization('fa');
    expect(l10n.history, 'تاریخچه');
    expect(l10n.historyToday, 'امروز');
    expect(l10n.historyYesterday, 'دیروز');
    expect(l10n.historyDaily, 'روزانه');
    expect(l10n.historyRetry, 'تلاش مجدد');
    expect(l10n.historyEmptyTitle, 'هنوز گفت‌وگویی ثبت نشده است');
    expect(l10n.historySedi, 'Sedi.');
  });

  test('Gate3Localization ar history labels', () {
    const l10n = Gate3Localization('ar');
    expect(l10n.history, 'السجل');
    expect(l10n.historyToday, 'اليوم');
    expect(l10n.historyYesterday, 'أمس');
    expect(l10n.historyMonthly, 'شهري');
    expect(l10n.historyRetry, 'إعادة المحاولة');
    expect(l10n.historyEmptyTitle, 'لا توجد محادثات مسجلة بعد');
  });

  test('Gate3Localization en history labels', () {
    const l10n = Gate3Localization('en');
    expect(l10n.history, 'History');
    expect(l10n.historyWeekly, 'Weekly');
    expect(l10n.isRtl, isFalse);
  });

  test('SediBrainOrb brand label is fixed Latin', () {
    expect(SediBrainOrb.brandLabel, 'Sedi.');
  });
}
