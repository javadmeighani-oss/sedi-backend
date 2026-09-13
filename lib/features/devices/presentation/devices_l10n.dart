import '../../../../core/locale/sedi_locale_controller.dart';

/// Gadgets / Devices presentation strings (en/fa/ar). Locale from SediLocaleController.
class DevicesL10n {
  final String lang;
  DevicesL10n([String? languageCode])
      : lang = languageCode ?? SediLocaleController.instance.languageCode;

  bool get isRtl => lang == 'fa' || lang == 'ar';

  String _t({required String en, required String fa, required String ar}) {
    switch (lang) {
      case 'fa':
        return fa;
      case 'ar':
        return ar;
      default:
        return en;
    }
  }

  String get title => _t(en: 'Gadgets', fa: 'گجت‌ها', ar: 'الأجهزة');
  String get myGadgets =>
      _t(en: 'My gadgets', fa: 'گجت‌های من', ar: 'أجهزتي');
  String get otherGadgets =>
      _t(en: 'Other gadgets', fa: 'گجت‌های دیگر', ar: 'أجهزة أخرى');
  String get unclassified =>
      _t(en: 'Unclassified', fa: 'طبقه‌بندی‌نشده', ar: 'غير مصنف');
  String get noGadgets =>
      _t(en: 'No gadgets', fa: 'گجتی نیست', ar: 'لا أجهزة');
  String get active => _t(en: 'Active', fa: 'فعال', ar: 'نشط');
  String get revoked => _t(en: 'Revoked', fa: 'باطل‌شده', ar: 'ملغى');
  String get rename => _t(en: 'Rename', fa: 'تغییر نام', ar: 'إعادة تسمية');
  String get save => _t(en: 'Save', fa: 'ذخیره', ar: 'حفظ');
  String get cancel => _t(en: 'Cancel', fa: 'لغو', ar: 'إلغاء');
  String get category => _t(en: 'Category', fa: 'دسته‌بندی', ar: 'الفئة');
  String get selfCategory => _t(en: 'SELF', fa: 'SELF', ar: 'SELF');
  String get otherCategory => _t(en: 'OTHER', fa: 'OTHER', ar: 'OTHER');
  String get labelHint => _t(
        en: 'Label (required for OTHER)',
        fa: 'برچسب (برای OTHER لازم است)',
        ar: 'التسمية (مطلوبة لـ OTHER)',
      );
  String get pleaseWait =>
      _t(en: 'Please wait.', fa: 'لطفاً صبر کنید.', ar: 'يرجى الانتظار.');
  String get connectComingSoon => _t(
        en: 'Connect (coming soon)',
        fa: 'اتصال (به‌زودی)',
        ar: 'اتصال (قريباً)',
      );
  String get presentationUpdated => _t(
        en: 'Presentation updated',
        fa: 'نمایش به‌روز شد',
        ar: 'تم تحديث العرض',
      );

  String statusLabel(String status) {
    final s = status.toLowerCase();
    if (s == 'revoked') return revoked;
    return active;
  }
}
