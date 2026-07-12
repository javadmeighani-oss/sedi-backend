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

  String get historyCardDescription => _t(
        en: 'Browse your past conversations with Sedi.',
        fa: 'گفت‌وگوهای قبلی خود با صدی را ببینید.',
        ar: 'تصفّح محادثاتك السابقة مع صدي.',
      );

  String get historyEmptyTitle => _t(
        en: 'No conversations yet',
        fa: 'هنوز گفت‌وگویی ثبت نشده است',
        ar: 'لا توجد محادثات مسجلة بعد',
      );

  String get historyEmptySubtitle => _t(
        en: 'Your chats with Sedi will appear here.',
        fa: 'گفت‌وگوهای شما با صدی اینجا نمایش داده می‌شود.',
        ar: 'ستظهر محادثاتك مع صدي هنا.',
      );

  String get historySignInRequired => _t(
        en: 'Please sign in to see your history',
        fa: 'برای مشاهده تاریخچه وارد حساب خود شوید',
        ar: 'يرجى تسجيل الدخول لعرض السجل',
      );

  String get historyRetry =>
      _t(en: 'Try again', fa: 'تلاش مجدد', ar: 'إعادة المحاولة');

  String get historyLoading =>
      _t(en: 'Loading…', fa: 'در حال بارگذاری…', ar: 'جارٍ التحميل…');

  String get historyDaily =>
      _t(en: 'Daily', fa: 'روزانه', ar: 'يومي');

  String get historyWeekly =>
      _t(en: 'Weekly', fa: 'هفتگی', ar: 'أسبوعي');

  String get historyMonthly =>
      _t(en: 'Monthly', fa: 'ماهانه', ar: 'شهري');

  String get historyYearly =>
      _t(en: 'Yearly', fa: 'سالانه', ar: 'سنوي');

  String get historyToday =>
      _t(en: 'Today', fa: 'امروز', ar: 'اليوم');

  String get historyYesterday =>
      _t(en: 'Yesterday', fa: 'دیروز', ar: 'أمس');

  String get historyYou => _t(en: 'You', fa: 'شما', ar: 'أنت');

  /// Fixed brand label — never translated.
  String get historySedi => 'Sedi.';

  String get historyGenericError => _t(
        en: 'Could not load history. Please try again.',
        fa: 'بارگذاری تاریخچه ممکن نشد. لطفاً دوباره تلاش کنید.',
        ar: 'تعذّر تحميل السجل. يرجى المحاولة مرة أخرى.',
      );

  String get historyBackToChat => _t(
        en: 'Back to chat',
        fa: 'بازگشت به گفتگو',
        ar: 'العودة إلى المحادثة',
      );

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

  String get camera => _t(en: 'Camera', fa: 'دوربین', ar: 'الكاميرا');

  String get photos => _t(en: 'Photos', fa: 'تصاویر', ar: 'الصور');

  String get files => _t(en: 'Files', fa: 'فایل‌ها', ar: 'الملفات');

  String get attachmentComingSoon => _t(
        en: 'Attachments will be available here soon.',
        fa: 'پیوست‌ها به‌زودی در این بخش در دسترس خواهند بود.',
        ar: 'ستتوفر المرفقات هنا قريبًا.',
      );

  String get readMore =>
      _t(en: 'Read more', fa: 'ادامه متن', ar: 'قراءة المزيد');

  String get showLess =>
      _t(en: 'Show less', fa: 'نمایش کمتر', ar: 'عرض أقل');

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
