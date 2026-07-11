/// Gate 3 section pages — localized strings (fa / ar / en).
class Gate3SectionsLocalization {
  final String lang;

  const Gate3SectionsLocalization(this.lang);

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

  String get settingsTitle => _t(en: 'Settings', fa: 'تنظیمات', ar: 'الإعدادات');
  String get closeContactsTitle =>
      _t(en: 'Close contacts', fa: 'تماس با نزدیکان', ar: 'جهات الاتصال المقربة');
  String get healthCareTitle =>
      _t(en: 'Health Care', fa: 'مراقبت سلامت', ar: 'الرعاية الصحية');
  String get lifestyleTitle =>
      _t(en: 'Lifestyle', fa: 'سبک زندگی', ar: 'نمط الحياة');
  String get gadgetsTitle => _t(en: 'Gadgets', fa: 'گجت‌ها', ar: 'الأجهزة');
  String get gadgetHubTitle => _t(
        en: 'Gadget Hub',
        fa: 'مرکز گجت صدی',
        ar: 'مركز أجهزة صدي',
      );

  String get backTooltip => _t(en: 'Back', fa: 'بازگشت', ar: 'رجوع');
  String get refresh => _t(en: 'Refresh', fa: 'به‌روزرسانی', ar: 'تحديث');
  String get loading =>
      _t(en: 'Loading…', fa: 'در حال بارگذاری…', ar: 'جارٍ التحميل…');
  String get retry => _t(en: 'Try again', fa: 'تلاش دوباره', ar: 'حاول مرة أخرى');
  String get lastUpdated => _t(
        en: 'Last updated',
        fa: 'آخرین به‌روزرسانی',
        ar: 'آخر تحديث',
      );

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
  String get close => _t(en: 'Close', fa: 'بستن', ar: 'إغلاق');

  String get noContactsTitle => _t(
        en: 'No close contacts yet',
        fa: 'هنوز مخاطب نزدیکی ثبت نشده',
        ar: 'لا توجد جهات اتصال مقربة بعد',
      );
  String get noContactsSubtitle => _t(
        en: 'Add someone you trust for updates and emergency reach-out.',
        fa: 'فرد مورد اعتماد خود را برای اطلاع‌رسانی و تماس اضطراری اضافه کنید.',
        ar: 'أضف شخصًا تثق به للتحديثات والاتصال في الطوارئ.',
      );
  String get addContact =>
      _t(en: 'Add contact', fa: 'افزودن مخاطب', ar: 'إضافة جهة اتصال');
  String get editContact =>
      _t(en: 'Edit contact', fa: 'ویرایش مخاطب', ar: 'تعديل جهة الاتصال');
  String get deleteContact =>
      _t(en: 'Remove contact', fa: 'حذف مخاطب', ar: 'إزالة جهة الاتصال');
  String get deleteContactConfirm => _t(
        en: 'Remove this contact?',
        fa: 'این مخاطب حذف شود؟',
        ar: 'هل تريد إزالة جهة الاتصال هذه؟',
      );
  String get cancel => _t(en: 'Cancel', fa: 'انصراف', ar: 'إلغاء');
  String get save => _t(en: 'Save', fa: 'ذخیره', ar: 'حفظ');
  String get nameLabel => _t(en: 'Name', fa: 'نام', ar: 'الاسم');
  String get phoneLabel => _t(en: 'Phone', fa: 'تلفن', ar: 'الهاتف');
  String get relationshipLabel =>
      _t(en: 'Relationship', fa: 'نسبت', ar: 'صلة القرابة');
  String get invalidPhone => _t(
        en: 'Enter a valid phone number.',
        fa: 'شماره تلفن معتبر وارد کنید.',
        ar: 'أدخل رقم هاتف صالحًا.',
      );
  String get nameRequired => _t(
        en: 'Name is required.',
        fa: 'نام الزامی است.',
        ar: 'الاسم مطلوب.',
      );
  String get saveFailed => _t(
        en: 'Could not save. Please try again.',
        fa: 'ذخیره نشد. لطفاً دوباره تلاش کنید.',
        ar: 'تعذر الحفظ. يرجى المحاولة مرة أخرى.',
      );
  String get saveSuccess => _t(
        en: 'Saved successfully.',
        fa: 'با موفقیت ذخیره شد.',
        ar: 'تم الحفظ بنجاح.',
      );

  String get prefDailyReport => _t(
        en: 'Daily health status',
        fa: 'گزارش روزانه وضعیت سلامت',
        ar: 'تقرير الحالة الصحية اليومي',
      );
  String get prefVitalAlerts => _t(
        en: 'Important vital alerts',
        fa: 'هشدار علائم حیاتی مهم',
        ar: 'تنبيهات العلامات الحيوية المهمة',
      );
  String get prefEmergencyBySedi => _t(
        en: 'Allow emergency contact by Sedi',
        fa: 'اجازه تماس اضطراری توسط صدی',
        ar: 'السماح لصدي بالاتصال في حالات الطوارئ',
      );
  String get prefCareSummary => _t(
        en: 'Care summary updates',
        fa: 'به‌روزرسانی‌های خلاصه مراقبت',
        ar: 'تحديثات ملخص الرعاية',
      );
  String get prefVitalAlertsUnavailable => _t(
        en: 'Notify this contact about important vital-sign changes when enabled.',
        fa: 'در صورت فعال‌سازی، این مخاطب از تغییرات مهم علائم حیاتی مطلع می‌شود.',
        ar: 'عند التفعيل، سيتم إخطار جهة الاتصال هذه بتغييرات العلامات الحيوية المهمة.',
      );
  String get emergencyExplanation => _t(
        en:
            'Sedi may contact this person when an emergency escalation policy is triggered and you have not responded to repeated reach-out attempts.',
        fa:
            'صدی ممکن است در صورت فعال شدن سیاست تشدید اضطراری و عدم پاسخ شما به تلاش‌های مکرر ارتباط، با این فرد تماس بگیرد.',
        ar:
            'قد يتصل صدي بهذا الشخص عند تفعيل سياسة التصعيد الطارئ وعدم استجابتك لمحاولات التواصل المتكررة.',
      );
  String get manualCall =>
      _t(en: 'Call', fa: 'تماس', ar: 'اتصال');
  String get manualCallUnavailable => _t(
        en: 'Phone dialer is not integrated in this build.',
        fa: 'شماره‌گیر در این نسخه یکپارچه نشده است.',
        ar: 'طالب الهاتف غير مدمج في هذا الإصدار.',
      );

  String get healthOverview =>
      _t(en: 'Health overview', fa: 'نمای کلی سلامت', ar: 'نظرة عامة على الصحة');
  String get vitalSigns =>
      _t(en: 'Vital signs', fa: 'علائم حیاتی', ar: 'العلامات الحيوية');
  String get medications =>
      _t(en: 'Medications', fa: 'داروها', ar: 'الأدوية');
  String get appointments =>
      _t(en: 'Appointments', fa: 'قرارها', ar: 'المواعيد');
  String get careInfo =>
      _t(en: 'Care information', fa: 'اطلاعات مراقبت', ar: 'معلومات الرعاية');
  String get noRecentData => _t(
        en: 'No recent data',
        fa: 'دادهٔ اخیر موجود نیست',
        ar: 'لا توجد بيانات حديثة',
      );
  String get lastUpdateUnavailable => _t(
        en: 'Last update unavailable',
        fa: 'زمان آخرین به‌روزرسانی نامشخص است',
        ar: 'وقت آخر تحديث غير متاح',
      );
  String get gadgetConnectionNotConfirmed => _t(
        en: 'Gadget connection not confirmed',
        fa: 'اتصال گجت تأیید نشده',
        ar: 'لم يتم تأكيد اتصال الجهاز',
      );
  String get heartRate => _t(en: 'Heart rate', fa: 'ضربان قلب', ar: 'معدل ضربات القلب');
  String get spo2 => _t(en: 'Oxygen', fa: 'اکسیژن خون', ar: 'الأكسجين');
  String get temperature => _t(en: 'Temperature', fa: 'دما', ar: 'درجة الحرارة');
  String get bloodPressure =>
      _t(en: 'Blood pressure', fa: 'فشار خون', ar: 'ضغط الدم');
  String get respiratoryRate => _t(
        en: 'Respiratory rate',
        fa: 'تعداد تنفس',
        ar: 'معدل التنفس',
      );
  String get sourceLabel => _t(en: 'Source', fa: 'منبع', ar: 'المصدر');
  String get staleData => _t(
        en: 'Data may be outdated',
        fa: 'داده ممکن است قدیمی باشد',
        ar: 'قد تكون البيانات قديمة',
      );
  String get reminderPlanned => _t(
        en: 'Reminders planned — not yet available',
        fa: 'یادآورها برنامه‌ریزی شده — هنوز فعال نیست',
        ar: 'التذكيرات مخططة — غير متاحة بعد',
      );
  String get noMedications => _t(
        en: 'No medications recorded',
        fa: 'دارویی ثبت نشده',
        ar: 'لا توجد أدوية مسجلة',
      );
  String get noAppointments => _t(
        en: 'No upcoming appointments',
        fa: 'قرار آینده‌ای ثبت نشده',
        ar: 'لا توجد مواعيد قادمة',
      );
  String get noCareItems => _t(
        en: 'No care recommendations yet',
        fa: 'هنوز توصیه مراقبتی ثبت نشده',
        ar: 'لا توجد توصيات رعاية بعد',
      );

  String get nutritionPlan =>
      _t(en: 'Nutrition', fa: 'تغذیه', ar: 'التغذية');
  String get exercisePlan =>
      _t(en: 'Exercise & movement', fa: 'ورزش و تحرک', ar: 'التمارين والحركة');
  String get habits => _t(en: 'Habits', fa: 'عادات', ar: 'العادات');
  String get goals => _t(en: 'Goals', fa: 'اهداف', ar: 'الأهداف');
  String get restrictions =>
      _t(en: 'Restrictions', fa: 'محدودیت‌ها', ar: 'القيود');
  String get dailyPlan => _t(en: 'Daily plan', fa: 'برنامه روزانه', ar: 'الخطة اليومية');
  String get weeklyPlan =>
      _t(en: 'Weekly plan', fa: 'برنامه هفتگی', ar: 'الخطة الأسبوعية');
  String get lifestyleActivities => _t(
        en: 'Upcoming activities',
        fa: 'فعالیت‌های پیش‌رو',
        ar: 'الأنشطة القادمة',
      );
  String get noLifestyleData => _t(
        en: 'No lifestyle data yet',
        fa: 'هنوز اطلاعات سبک زندگی ثبت نشده',
        ar: 'لا توجد بيانات نمط حياة بعد',
      );
  String get lifestyleNotificationsPlanned => _t(
        en: 'Lifestyle reminders will be managed by Sedi notifications.',
        fa: 'یادآورهای سبک زندگی از طریق اعلان‌های صدی مدیریت خواهند شد.',
        ar: 'ستُدار تذكيرات نمط الحياة عبر إشعارات صدي.',
      );

  String get hubStatus =>
      _t(en: 'Hub status', fa: 'وضعیت مرکز گجت', ar: 'حالة المركز');
  String get connectedSensors =>
      _t(en: 'Connected sensors', fa: 'سنسورهای متصل', ar: 'المستشعرات المتصلة');
  String get noHubRegistered => _t(
        en: 'No Gadget Hub registered',
        fa: 'مرکز گجت ثبت نشده',
        ar: 'لم يتم تسجيل مركز الأجهزة',
      );
  String get noSensors => _t(
        en: 'No sensors connected',
        fa: 'سنسوری متصل نیست',
        ar: 'لا توجد مستشعرات متصلة',
      );
  String get statusUnavailable => _t(
        en: 'Status unavailable',
        fa: 'وضعیت در دسترس نیست',
        ar: 'الحالة غير متاحة',
      );

  String get batteryLabel => _t(en: 'Battery', fa: 'باتری', ar: 'البطارية');
  String get syncLabel => _t(en: 'Last sync', fa: 'آخرین همگام‌سازی', ar: 'آخر مزامنة');

  String hubStatusLabel(String status) {
    switch (status) {
      case 'connected':
        return _t(en: 'Connected', fa: 'متصل', ar: 'متصل');
      case 'recently_seen':
        return _t(en: 'Recently seen', fa: 'اخیراً دیده شده', ar: 'شوهد مؤخرًا');
      case 'disconnected':
        return _t(en: 'Disconnected', fa: 'قطع شده', ar: 'غير متصل');
      case 'revoked':
        return _t(en: 'Revoked', fa: 'لغو شده', ar: 'ملغى');
      case 'not_registered':
        return _t(en: 'Not registered', fa: 'ثبت نشده', ar: 'غير مسجل');
      default:
        return _t(en: 'Unknown', fa: 'نامشخص', ar: 'غير معروف');
    }
  }

  String monitoringStateLabel(String state) {
    switch (state) {
      case 'active':
        return _t(en: 'Active monitoring', fa: 'پایش فعال', ar: 'مراقبة نشطة');
      case 'recent':
        return _t(en: 'Recent data', fa: 'داده اخیر', ar: 'بيانات حديثة');
      case 'stale':
        return _t(en: 'Stale data', fa: 'داده قدیمی', ar: 'بيانات قديمة');
      case 'disconnected':
        return _t(en: 'Disconnected', fa: 'قطع اتصال', ar: 'غير متصل');
      case 'no_data':
        return _t(en: 'No data', fa: 'بدون داده', ar: 'لا توجد بيانات');
      default:
        return _t(en: 'Unknown', fa: 'نامشخص', ar: 'غير معروف');
    }
  }

  String get editSchedule =>
      _t(en: 'Edit schedule', fa: 'ویرایش زمان‌بندی', ar: 'تعديل الجدول');
  String get reminderTimesLabel =>
      _t(en: 'Reminder times (HH:MM)', fa: 'زمان یادآور (HH:MM)', ar: 'أوقات التذكير');
  String get intervalHoursLabel =>
      _t(en: 'Interval (hours)', fa: 'فاصله (ساعت)', ar: 'الفاصل (ساعات)');
  String get timezoneLabel =>
      _t(en: 'Timezone', fa: 'منطقه زمانی', ar: 'المنطقة الزمنية');
  String get stockLevelLabel =>
      _t(en: 'Stock', fa: 'موجودی', ar: 'المخزون');
  String get lastSignalLabel =>
      _t(en: 'Last signal', fa: 'آخرین سیگنال', ar: 'آخر إشارة');
  String get reminderEnabledLabel =>
      _t(en: 'Reminders on', fa: 'یادآور فعال', ar: 'التذكيرات مفعّلة');
  String get weeklySectionEmpty => _t(
        en: 'No weekly plan items recorded.',
        fa: 'مورد برنامه هفتگی ثبت نشده.',
        ar: 'لا توجد عناصر خطة أسبوعية مسجلة.',
      );

  String genericError() => _t(
        en: 'Something went wrong. Please try again.',
        fa: 'مشکلی پیش آمد. لطفاً دوباره تلاش کنید.',
        ar: 'حدث خطأ. يرجى المحاولة مرة أخرى.',
      );
  String networkError() => _t(
        en: 'Could not reach the server. Check your connection.',
        fa: 'ارتباط با سرور برقرار نشد. اتصال اینترنت را بررسی کنید.',
        ar: 'تعذر الوصول إلى الخادم. تحقق من الاتصال.',
      );
}
