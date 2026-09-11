import '../../../core/locale/calendar_date_math.dart';
import '../../../core/locale/sedi_locale_registry.dart';

/// Birth-date calendar helpers for Gate 2 (Jalali, Gregorian, Hijri).
class BirthCalendarHelper {
  BirthCalendarHelper._();

  static String calendarTypeForLanguage(String lang) {
    return SediLocaleRegistry.resolve(lang).defaultCalendar;
  }

  static int daysInMonth({
    required String calendarType,
    required int year,
    required int month,
  }) {
    switch (calendarType) {
      case 'jalali':
        return CalendarDateMath.jalaliMonthLength(year, month);
      case 'hijri':
        return CalendarDateMath.hijriMonthLength(year, month);
      default:
        return DateTime(year, month + 1, 0).day;
    }
  }

  static List<int> yearRange(String calendarType) {
    final now = DateTime.now();
    switch (calendarType) {
      case 'jalali':
        final jNow =
            CalendarDateMath.gregorianToJalali(now.year, now.month, now.day);
        return List<int>.generate(jNow[0] - 1300 + 1, (i) => jNow[0] - i);
      case 'hijri':
        final hNow =
            CalendarDateMath.gregorianToHijri(now.year, now.month, now.day);
        return List<int>.generate(hNow[0] - 1350 + 1, (i) => hNow[0] - i);
      default:
        return List<int>.generate(
          now.year - 1900 + 1,
          (i) => now.year - i,
        );
    }
  }

  static List<int> defaultSelection(String calendarType) {
    switch (calendarType) {
      case 'jalali':
        return [1, 1, 1370];
      case 'hijri':
        return [1, 1, 1411];
      default:
        return [1, 1, 1990];
    }
  }

  /// Returns ISO `YYYY-MM-DD` or null if conversion fails.
  static String? toIsoDate({
    required String calendarType,
    required int day,
    required int month,
    required int year,
  }) {
    try {
      final List<int> g;
      switch (calendarType) {
        case 'jalali':
          g = CalendarDateMath.jalaliToGregorian(year, month, day);
        case 'hijri':
          g = CalendarDateMath.hijriToGregorian(year, month, day);
        default:
          g = [year, month, day];
      }
      final dt = DateTime(g[0], g[1], g[2]);
      final mm = dt.month.toString().padLeft(2, '0');
      final dd = dt.day.toString().padLeft(2, '0');
      return '${dt.year}-$mm-$dd';
    } catch (_) {
      return null;
    }
  }

  // --- Public conversion API (delegates to CalendarDateMath) ---

  static List<int> jalaliToGregorian(int jy, int jm, int jd) =>
      CalendarDateMath.jalaliToGregorian(jy, jm, jd);

  static List<int> gregorianToJalali(int gy, int gm, int gd) =>
      CalendarDateMath.gregorianToJalali(gy, gm, gd);

  static List<int> hijriToGregorian(int hy, int hm, int hd) =>
      CalendarDateMath.hijriToGregorian(hy, hm, hd);

  static List<int> gregorianToHijri(int gy, int gm, int gd) =>
      CalendarDateMath.gregorianToHijri(gy, gm, gd);
}
