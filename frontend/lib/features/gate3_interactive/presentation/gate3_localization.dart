import '../../../core/utils/brand_name.dart';

/// Gate 3 localized strings (fa / ar / en).
class Gate3Localization {
  final String lang;

  const Gate3Localization(this.lang);

  bool get isRtl => lang == 'fa' || lang == 'ar';

  String get notifications =>
      _t(en: 'Notifications', fa: 'اعلان‌ها', ar: 'الإشعارات');

  String get healthCare =>
      _t(en: 'Health Care', fa: 'مراقبت سلامت', ar: 'الرعاية الصحية');

  String get lifestyle =>
      _t(en: 'Lifestyle', fa: 'سبک زندگی', ar: 'نمط الحياة');

  String get gadgets => _t(en: 'Gadgets', fa: 'گجت‌ها', ar: 'الأجهزة');

  String get history => _t(en: 'History', fa: 'تاریخچه', ar: 'السجل');

  String get settings => _t(en: 'Settings', fa: 'تنظیمات', ar: 'الإعدادات');

  String get editProfile => _t(
        en: 'Edit profile',
        fa: 'ویرایش پروفایل',
        ar: 'تعديل الملف الشخصي',
      );

  String get logout => _t(en: 'Log out', fa: 'خروج', ar: 'تسجيل الخروج');

  String get profileSettingsPlaceholder => _t(
        en: 'Profile settings will be available here soon.',
        fa: 'تنظیمات پروفایل به‌زودی در این بخش در دسترس خواهد بود.',
        ar: 'ستتوفر إعدادات الملف الشخصي هنا قريبًا.',
      );

  String get composerPlaceholderFa => 'صحبت با صدی';

  String get composerPlaceholder {
    if (lang == 'fa') return composerPlaceholderFa;
    if (lang == 'ar') return 'تحدث مع صدي';
    return 'Talk to Sedi';
  }

  String get microphonePermissionRequired => _t(
        en: 'Microphone permission required',
        fa: 'دسترسی به میکروفون لازم است',
        ar: 'مطلوب إذن الميكروفون',
      );

  String get pressBackAgainToExit => _t(
        en: 'Press back again to exit',
        fa: 'برای خروج دوباره back بزنید',
        ar: 'اضغط رجوع مرة أخرى للخروج',
      );

  String get returnToLatest =>
      _t(en: 'Latest', fa: 'آخرین', ar: 'الأحدث');

  String get close => _t(en: 'Close', fa: 'بستن', ar: 'إغلاق');

  String sampleIntroAssistant1() {
    final brand = sediBrandName(lang);
    return _t(
      en: 'Hello, I\'m $brand — your trusted health companion.',
      fa: 'سلام، من $brand‌ام — همراه هوشمند سلامت شما.',
      ar: 'مرحبًا، أنا $brand — رفيقك الموثوق في الصحة.',
    );
  }

  String sampleIntroUser1() => _t(
        en: 'Hi Sedi. I\'m not feeling well today.',
        fa: 'سلام صدی. امروز حالم خوب نیست.',
        ar: 'مرحبًا صدي. لا أشعر بحالة جيدة اليوم.',
      );

  String sampleIntroAssistant2() => _t(
        en: 'Share your symptoms and I\'ll guide you.',
        fa: 'علائمت را بگو تا دقیق‌تر راهنماییت کنم.',
        ar: 'شاركني أعراضك لأرشدك بدقة.',
      );

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
}
