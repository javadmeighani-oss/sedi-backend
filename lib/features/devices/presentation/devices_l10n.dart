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
  String get connect => _t(en: 'Connect', fa: 'اتصال', ar: 'اتصال');
  String get disconnect => _t(en: 'Disconnect', fa: 'قطع اتصال', ar: 'قطع');
  String get scanning => _t(en: 'Scanning…', fa: 'در حال جستجو…', ar: 'جارٍ البحث…');
  String get setupCodeHint => _t(
        en: '4-digit Setup Code',
        fa: 'کد راه‌اندازی ۴ رقمی',
        ar: 'رمز الإعداد المكوّن من 4 أرقام',
      );
  String get selectDevice =>
      _t(en: 'Select gadget', fa: 'انتخاب گجت', ar: 'اختر الجهاز');
  String get bleConnected =>
      _t(en: 'Connected', fa: 'متصل', ar: 'متصل');
  String get bleConnecting =>
      _t(en: 'Connecting', fa: 'در حال اتصال', ar: 'جارٍ الاتصال');
  String get bleReconnecting =>
      _t(en: 'Reconnecting', fa: 'اتصال مجدد', ar: 'إعادة الاتصال');
  String get bleOutOfRange =>
      _t(en: 'Out of range', fa: 'خارج محدوده', ar: 'خارج النطاق');
  String get bleDisconnected =>
      _t(en: 'Disconnected', fa: 'قطع‌شده', ar: 'غير متصل');
  String get battery => _t(en: 'Battery', fa: 'باتری', ar: 'البطارية');
  String get contact => _t(en: 'Contact', fa: 'تماس', ar: 'التلامس');
  String get presentationUpdated => _t(
        en: 'Presentation updated',
        fa: 'نمایش به‌روز شد',
        ar: 'تم تحديث العرض',
      );

  String transportLabel(String state) {
    switch (state) {
      case 'connected':
        return bleConnected;
      case 'connecting':
        return bleConnecting;
      case 'reconnecting':
        return bleReconnecting;
      case 'outOfRange':
        return bleOutOfRange;
      default:
        return bleDisconnected;
    }
  }

  String statusLabel(String status) {
    final s = status.toLowerCase();
    if (s == 'revoked') return revoked;
    return active;
  }
}
