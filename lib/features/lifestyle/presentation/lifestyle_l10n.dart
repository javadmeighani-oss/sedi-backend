import '../../../../core/locale/sedi_locale_controller.dart';

/// Lifestyle hub localization (en/fa/ar). Presentation only.
class LifestyleL10n {
  final String lang;
  LifestyleL10n([String? languageCode])
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

  String get title => _t(en: 'Lifestyle', fa: 'سبک زندگی', ar: 'نمط الحياة');
  String get health => _t(en: 'Health', fa: 'سلامت', ar: 'الصحة');
  String get myHistory => _t(en: 'My History', fa: 'تاریخچه من', ar: 'سجلي');
  String get mySchedule =>
      _t(en: 'My Schedule', fa: 'برنامه من', ar: 'جدولي');
  String get nutritionPlan =>
      _t(en: 'Nutrition Plan', fa: 'برنامه تغذیه', ar: 'خطة التغذية');
  String get exercisePlan =>
      _t(en: 'Exercise Plan', fa: 'برنامه ورزش', ar: 'خطة التمرين');

  List<String> get sectionTitles =>
      [health, myHistory, mySchedule, nutritionPlan, exercisePlan];

  String get hrStable =>
      _t(en: 'Stable pattern', fa: 'الگوی پایدار', ar: 'نمط مستقر');
  String get hrUnstable =>
      _t(en: 'Unstable pattern', fa: 'الگوی ناپایدار', ar: 'نمط غير مستقر');
  String get hrChanged =>
      _t(en: 'Change detected', fa: 'تغییر مشاهده شد', ar: 'تم رصد تغيير');
  String get hrInsufficient =>
      _t(en: 'Not enough data', fa: 'داده کافی نیست', ar: 'بيانات غير كافية');
  String get latestHr =>
      _t(en: 'Latest heart rate', fa: 'آخرین ضربان', ar: 'آخر معدل نبض');
  String get lastReceived =>
      _t(en: 'Last received', fa: 'آخرین دریافت', ar: 'آخر استلام');
  String get historyRange =>
      _t(en: 'History range', fa: 'بازه تاریخچه', ar: 'نطاق السجل');
  String get range7d => _t(en: '7 days', fa: '۷ روز', ar: '٧ أيام');
  String get range30d => _t(en: '30 days', fa: '۳۰ روز', ar: '٣٠ يوماً');
  String get range3m => _t(en: '3 months', fa: '۳ ماه', ar: '٣ أشهر');
  String get range1y =>
      _t(en: '1 year / available', fa: '۱ سال / موجود', ar: 'سنة / المتاح');
  String get availableFrom =>
      _t(en: 'Available from', fa: 'موجود از', ar: 'متاح من');
  String get availableTo => _t(en: 'Available to', fa: 'موجود تا', ar: 'متاح إلى');
  String get noHrData =>
      _t(en: 'No heart-rate data yet.', fa: 'هنوز داده ضربان نیست.', ar: 'لا بيانات نبض بعد.');

  String get recentConversations => _t(
        en: 'Recent conversations',
        fa: 'گفتگوهای اخیر',
        ar: 'المحادثات الأخيرة',
      );
  String get sediSummaries =>
      _t(en: 'Sedi summaries', fa: 'خلاصه‌های صدی', ar: 'ملخصات سدي');
  String get historyExplain => _t(
        en: 'Recent raw conversations are available here for the retained period. For older topics, ask Sedi in Chat.',
        fa: 'گفتگوهای خام اخیر در دوره نگهداری اینجا هستند. برای موضوعات قدیمی‌تر در چت از صدی بپرسید.',
        ar: 'المحادثات الخام الحديثة متاحة لفترة الاحتفاظ. للمواضيع الأقدم اسأل سدي في الدردشة.',
      );
  String get daily => _t(en: 'Daily', fa: 'روزانه', ar: 'يومي');
  String get weekly => _t(en: 'Weekly', fa: 'هفتگی', ar: 'أسبوعي');
  String get monthly => _t(en: 'Monthly', fa: 'ماهانه', ar: 'شهري');
  String get yearly => _t(en: 'Yearly', fa: 'سالانه', ar: 'سنوي');
  String get noSummary =>
      _t(en: 'No summary yet.', fa: 'هنوز خلاصه‌ای نیست.', ar: 'لا ملخص بعد.');
  String get openChat =>
      _t(en: 'Talk to Sedi', fa: 'صحبت با صدی', ar: 'تحدث إلى سدي');

  String get today => _t(en: 'Today', fa: 'امروز', ar: 'اليوم');
  String get tomorrow => _t(en: 'Tomorrow', fa: 'فردا', ar: 'غداً');
  String get thisWeek => _t(en: 'This week', fa: 'این هفته', ar: 'هذا الأسبوع');
  String get later => _t(en: 'Later', fa: 'بعداً', ar: 'لاحقاً');
  String get governedActions => _t(
        en: 'Governed actions',
        fa: 'اقدامات هدایت‌شده',
        ar: 'إجراءات محكومة',
      );
  String get reminder => _t(en: 'Reminder', fa: 'یادآور', ar: 'تذكير');
  String get reminderOff => _t(en: 'Off', fa: 'خاموش', ar: 'إيقاف');
  String get reminderAtTime =>
      _t(en: 'At event time', fa: 'در زمان رویداد', ar: 'وقت الحدث');
  String get reminder15 =>
      _t(en: '15 min before', fa: '۱۵ دقیقه قبل', ar: 'قبل ١٥ دقيقة');
  String get reminder30 =>
      _t(en: '30 min before', fa: '۳۰ دقیقه قبل', ar: 'قبل ٣٠ دقيقة');
  String get reminder1h =>
      _t(en: '1 hour before', fa: '۱ ساعت قبل', ar: 'قبل ساعة');
  String get reminder1d =>
      _t(en: '1 day before', fa: '۱ روز قبل', ar: 'قبل يوم');
  String get noEvents =>
      _t(en: 'No scheduled items.', fa: 'رویدادی نیست.', ar: 'لا عناصر مجدولة.');

  String get noNutrition => _t(
        en: 'No nutrition plan yet.',
        fa: 'هنوز برنامه تغذیه نیست.',
        ar: 'لا خطة تغذية بعد.',
      );
  String get noExercise => _t(
        en: 'No exercise plan yet.',
        fa: 'هنوز برنامه ورزش نیست.',
        ar: 'لا خطة تمرين بعد.',
      );
  String get talkToCreate => _t(
        en: 'Talk to Sedi to create your plan.',
        fa: 'برای ساخت برنامه با صدی صحبت کنید.',
        ar: 'تحدث إلى سدي لإنشاء خطتك.',
      );
  String get breakfast => _t(en: 'Breakfast', fa: 'صبحانه', ar: 'فطور');
  String get lunch => _t(en: 'Lunch', fa: 'ناهار', ar: 'غداء');
  String get dinner => _t(en: 'Dinner', fa: 'شام', ar: 'عشاء');
  String get snack => _t(en: 'Snack', fa: 'میان‌وعده', ar: 'وجبة خفيفة');

  String get nutritionActive => _t(
        en: 'Your nutrition plan',
        fa: 'برنامه تغذیه شما',
        ar: 'خطة التغذية الخاصة بك',
      );
  String get exerciseActive => _t(
        en: 'Your exercise plan',
        fa: 'برنامه ورزش شما',
        ar: 'خطة التمرين الخاصة بك',
      );
  String get reviewDueTitle => _t(
        en: 'Plan review due',
        fa: 'زمان بازبینی برنامه',
        ar: 'حان وقت مراجعة الخطة',
      );
  String get reviewDueBody => _t(
        en: 'Your current cycle has ended. Review with Sedi when ready.',
        fa: 'چرخه فعلی به پایان رسیده است. وقتی آماده بودید با صدی بازبینی کنید.',
        ar: 'انتهت دورتك الحالية. راجع مع سدي عندما تكون جاهزاً.',
      );
  String get planUnavailable => _t(
        en: 'Plan unavailable',
        fa: 'برنامه در دسترس نیست',
        ar: 'الخطة غير متاحة',
      );
  String get planUnavailableBody => _t(
        en: 'Could not load your weekly plan right now.',
        fa: 'فعلاً نمی‌توان برنامه هفتگی را بارگذاری کرد.',
        ar: 'تعذر تحميل خطتك الأسبوعية الآن.',
      );
  String get noActionsThisDay => _t(
        en: 'No items for this day.',
        fa: 'موردی برای این روز نیست.',
        ar: 'لا عناصر لهذا اليوم.',
      );
  /// Contextual assistant starter (not composer draft; not auto-submitted).
  String get nutritionChatStarter => _t(
        en:
            'If you like, we can review your nutrition plan together and improve it for your goals. Where would you like to start?',
        fa:
            'اگر بخواهی، می‌توانیم برنامه تغذیه‌ات را با هم مرور کنیم و متناسب با هدفت بهترش کنیم. دوست داری از کجا شروع کنیم؟',
        ar:
            'إذا رغبت، يمكننا مراجعة خطة تغذيتك معًا وتحسينها بما يناسب هدفك. من أين تحب أن نبدأ؟',
      );
  String get exerciseChatStarter => _t(
        en:
            'If you like, we can review your exercise plan together and adjust it to your situation and goals. Where would you like to start?',
        fa:
            'اگر بخواهی، می‌توانیم برنامه ورزشی‌ات را با هم مرور کنیم و متناسب با شرایط و هدفت تنظیمش کنیم. دوست داری از کجا شروع کنیم؟',
        ar:
            'إذا رغبت، يمكننا مراجعة خطة تمرينك معًا وتعديلها بما يناسب وضعك وهدفك. من أين تحب أن نبدأ؟',
      );

  String cycleRangeLabel(String start, String end) {
    if (end.isEmpty) {
      return _t(
        en: 'Cycle from $start',
        fa: 'چرخه از $start',
        ar: 'الدورة من $start',
      );
    }
    return _t(
      en: 'Cycle $start – $end',
      fa: 'چرخه $start – $end',
      ar: 'الدورة $start – $end',
    );
  }

  /// ISO weekday: 1=Monday … 7=Sunday (from backend local_date).
  String weekdayShort(int isoWeekday) {
    switch (isoWeekday) {
      case 1:
        return _t(en: 'Mon', fa: 'دوشنبه', ar: 'الإثنين');
      case 2:
        return _t(en: 'Tue', fa: 'سه‌شنبه', ar: 'الثلاثاء');
      case 3:
        return _t(en: 'Wed', fa: 'چهارشنبه', ar: 'الأربعاء');
      case 4:
        return _t(en: 'Thu', fa: 'پنجشنبه', ar: 'الخميس');
      case 5:
        return _t(en: 'Fri', fa: 'جمعه', ar: 'الجمعة');
      case 6:
        return _t(en: 'Sat', fa: 'شنبه', ar: 'السبت');
      case 7:
        return _t(en: 'Sun', fa: 'یکشنبه', ar: 'الأحد');
      default:
        return '';
    }
  }

  String mealSlotLabel(String slot) {
    switch (slot.toLowerCase()) {
      case 'breakfast':
        return breakfast;
      case 'lunch':
        return lunch;
      case 'dinner':
        return dinner;
      case 'snack':
        return snack;
      default:
        return slot;
    }
  }

  String durationMinutes(int minutes) => _t(
        en: '$minutes min',
        fa: '$minutes دقیقه',
        ar: '$minutes دقيقة',
      );

  /// Labels for DEVICE_REPORTED STABLE|UNSTABLE only (presentation).
  String deviceReportedHrStatusLabel(String code) {
    switch (code.toUpperCase()) {
      case 'STABLE':
        return hrStable;
      case 'UNSTABLE':
        return hrUnstable;
      default:
        return hrInsufficient;
    }
  }

  String hrStatusLabel(String code) {
    switch (code) {
      case 'STABLE':
        return hrStable;
      case 'UNSTABLE':
        return hrUnstable;
      case 'UNSTABLE_OR_CHANGED':
        return hrChanged;
      default:
        return hrInsufficient;
    }
  }

  String scheduleStatusLabel(String code) {
    switch (code.toLowerCase()) {
      case 'done':
      case 'completed':
        return _t(en: 'Done', fa: 'انجام شد', ar: 'تم');
      case 'postponed':
        return _t(en: 'Postponed', fa: 'به تعویق افتاد', ar: 'مؤجل');
      case 'cancelled':
        return _t(en: 'Cancelled', fa: 'لغو شد', ar: 'ملغى');
      default:
        return _t(en: 'Upcoming', fa: 'پیش‌رو', ar: 'قادم');
    }
  }
}
