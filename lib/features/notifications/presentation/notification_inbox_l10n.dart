import '../../../core/locale/sedi_locale_controller.dart';

/// A3 Smart Notifications Inbox localization (en/fa/ar). Presentation only.
/// Does not translate backend-supplied notification title/body content.
class NotificationInboxL10n {
  final String lang;
  NotificationInboxL10n([String? languageCode])
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

  String get title =>
      _t(en: 'Notifications', fa: 'اعلان‌ها', ar: 'الإشعارات');

  String get filterAll => _t(en: 'All', fa: 'همه', ar: 'الكل');

  String get filterUnread =>
      _t(en: 'Unread', fa: 'خوانده‌نشده', ar: 'غير مقروء');

  String get loading => _t(
        en: 'Loading notifications...',
        fa: 'در حال بارگذاری اعلان‌ها...',
        ar: 'جاري تحميل الإشعارات...',
      );

  String get emptyTitle => _t(
        en: 'No sent notifications in this history window',
        fa: 'هیچ اعلان ارسال‌شده‌ای در این بازه تاریخچه نیست',
        ar: 'لا إشعارات مُرسلة في نافذة السجل هذه',
      );

  String get emptySubtitle => _t(
        en: 'Scheduled or failed notifications are not shown here.',
        fa: 'اعلان‌های زمان‌بندی‌شده یا ناموفق اینجا نشان داده نمی‌شوند.',
        ar: 'الإشعارات المجدولة أو الفاشلة لا تُعرض هنا.',
      );

  String get fallbackTitle =>
      _t(en: 'Notification', fa: 'اعلان', ar: 'إشعار');

  String get noDetails =>
      _t(en: 'No details', fa: 'بدون جزئیات', ar: 'بدون تفاصيل');

  String get markAsRead =>
      _t(en: 'Mark as read', fa: 'علامت به‌عنوان خوانده‌شده', ar: 'تعيين كمقروء');

  String get like => _t(en: 'Like', fa: 'پسندیدن', ar: 'إعجاب');

  String get dislike => _t(en: 'Dislike', fa: 'نپسندیدن', ar: 'عدم إعجاب');

  String get continueInChat =>
      _t(en: 'Continue with Sedi', fa: 'ادامه با صدی', ar: 'المتابعة مع سدي');

  String get wasThisUseful =>
      _t(en: 'Was this useful?', fa: 'آیا مفید بود؟', ar: 'هل كان هذا مفيداً؟');

  String get dislikeReasonTitle =>
      _t(en: 'Why was this not useful?', fa: 'چرا مفید نبود؟', ar: 'لماذا لم يكن مفيداً؟');

  String get dislikeReasonTooFrequent =>
      _t(en: 'Too frequent', fa: 'خیلی زیاد بود', ar: 'متكرر جداً');

  String get dislikeReasonIrrelevant =>
      _t(en: 'Irrelevant', fa: 'مرتبط نبود', ar: 'غير ذي صلة');

  String get dislikeReasonUnclear =>
      _t(en: 'Unclear', fa: 'واضح نبود', ar: 'غير واضح');

  String get dislikeReasonSkip =>
      _t(en: 'Skip reason', fa: 'بدون دلیل', ar: 'بدون سبب');

  String get now => _t(en: 'Now', fa: 'الان', ar: 'الآن');

  String minutesAgo(int n) => _t(
        en: '${n}m',
        fa: '$nد',
        ar: '$nد',
      );

  String hoursAgo(int n) => _t(
        en: '${n}h',
        fa: '$nس',
        ar: '$nس',
      );

  String daysAgo(int n) => _t(
        en: '${n}d',
        fa: '$nر',
        ar: '$nي',
      );

  String relativeTime(DateTime dt) {
    final diff = DateTime.now().difference(dt);
    if (diff.inMinutes < 1) return now;
    if (diff.inMinutes < 60) return minutesAgo(diff.inMinutes);
    if (diff.inHours < 24) return hoursAgo(diff.inHours);
    if (diff.inDays < 7) return daysAgo(diff.inDays);
    return '${dt.month}/${dt.day}';
  }
}
