import '../../../core/locale/sedi_locale_registry.dart';
import '../../../core/utils/brand_name.dart';

/// Gate 3 localized strings — presentation adaptor only.
/// Language authority is [SediLocaleController] / Account.preferred_language.
class Gate3Localization {
  final String lang;

  const Gate3Localization(this.lang);

  bool get isRtl => SediLocaleRegistry.resolve(lang).isRtl;

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

  String get profileNameLabel =>
      _t(en: 'Name', fa: 'نام', ar: 'الاسم');
  String get profileDobLabel =>
      _t(en: 'Date of birth', fa: 'تاریخ تولد', ar: 'تاريخ الميلاد');
  String get profileSexLabel =>
      _t(en: 'Sex', fa: 'جنسیت', ar: 'الجنس');
  String get profilePhoneLabel =>
      _t(en: 'Phone', fa: 'شماره همراه', ar: 'الهاتف');
  String get changePhone =>
      _t(en: 'Change phone', fa: 'تغییر شماره', ar: 'تغيير الهاتف');
  String get newPhoneLabel =>
      _t(en: 'New phone number', fa: 'شماره جدید', ar: 'رقم جديد');
  String get sendPhoneOtp =>
      _t(en: 'Send code', fa: 'ارسال کد', ar: 'إرسال الرمز');
  String get verifyPhoneOtp =>
      _t(en: 'Verify', fa: 'تأیید', ar: 'تحقق');
  String get otpCodeLabel =>
      _t(en: 'OTP code', fa: 'کد تأیید', ar: 'رمز التحقق');
  String get phoneChangeSuccess => _t(
        en: 'Phone updated.',
        fa: 'شماره به‌روز شد.',
        ar: 'تم تحديث الهاتف.',
      );
  String get phoneInvalid => _t(
        en: 'Enter a valid phone number.',
        fa: 'شماره معتبر وارد کنید.',
        ar: 'أدخل رقم هاتف صالحًا.',
      );
  String get phoneSame => _t(
        en: 'That is already your current number.',
        fa: 'این همان شماره فعلی شماست.',
        ar: 'هذا هو رقمك الحالي بالفعل.',
      );
  String get phoneDuplicate => _t(
        en: 'This number is already in use.',
        fa: 'این شماره قبلاً استفاده شده است.',
        ar: 'هذا الرقم مستخدم بالفعل.',
      );
  String get phoneOtpInvalid =>
      _t(en: 'Incorrect code.', fa: 'کد نادرست است.', ar: 'رمز غير صحيح.');
  String get phoneOtpExpired =>
      _t(en: 'Code expired.', fa: 'کد منقضی شده است.', ar: 'انتهت صلاحية الرمز.');
  String get phoneOtpRateLimited => _t(
        en: 'Too many requests. Try again later.',
        fa: 'درخواست‌های زیاد. بعداً تلاش کنید.',
        ar: 'طلبات كثيرة. حاول لاحقًا.',
      );
  String get phoneChangeNetworkError => _t(
        en: 'Network error. Try again.',
        fa: 'خطای شبکه. دوباره تلاش کنید.',
        ar: 'خطأ في الشبكة. حاول مرة أخرى.',
      );
  String get cancel => _t(en: 'Cancel', fa: 'انصراف', ar: 'إلغاء');
  String get whatSediKnows => _t(
        en: 'What Sedi knows about me',
        fa: 'آنچه صدی درباره من می‌داند',
        ar: 'ما تعرفه صدي عني',
      );
  String get whatSediKnowsEmpty => _t(
        en: 'No saved facts yet.',
        fa: 'هنوز حقیقت ذخیره‌شده‌ای نیست.',
        ar: 'لا توجد حقائق محفوظة بعد.',
      );

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

  String get camera => _t(en: 'Camera', fa: 'دوربین', ar: 'الكاميرا');

  String get photos => _t(en: 'Photos', fa: 'تصاویر', ar: 'الصور');

  String get files => _t(en: 'Files', fa: 'فایل‌ها', ar: 'الملفات');

  String get attachmentComingSoon => _t(
        en: 'Attachments will be available here soon.',
        fa: 'پیوست‌ها به‌زودی در این بخش در دسترس خواهند بود.',
        ar: 'ستتوفر المرفقات هنا قريبًا.',
      );

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
