/// Birth-date calendar helpers for Gate 2 (Jalali, Gregorian, Hijri).
class BirthCalendarHelper {
  BirthCalendarHelper._();

  static String calendarTypeForLanguage(String lang) {
    switch (lang) {
      case 'fa':
        return 'jalali';
      case 'ar':
        return 'hijri';
      default:
        return 'gregorian';
    }
  }

  static int daysInMonth({
    required String calendarType,
    required int year,
    required int month,
  }) {
    switch (calendarType) {
      case 'jalali':
        return _jalaliMonthLength(year, month);
      case 'hijri':
        return _hijriMonthLength(year, month);
      default:
        return DateTime(year, month + 1, 0).day;
    }
  }

  static List<int> yearRange(String calendarType) {
    final now = DateTime.now();
    switch (calendarType) {
      case 'jalali':
        final jNow = gregorianToJalali(now.year, now.month, now.day);
        return List<int>.generate(jNow[0] - 1300 + 1, (i) => jNow[0] - i);
      case 'hijri':
        final hNow = gregorianToHijri(now.year, now.month, now.day);
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
          g = jalaliToGregorian(year, month, day);
        case 'hijri':
          g = hijriToGregorian(year, month, day);
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

  // --- Jalali (Persian Solar) ---

  static int _jalaliMonthLength(int jy, int jm) {
    if (jm <= 6) return 31;
    if (jm <= 11) return 30;
    return _isJalaliLeap(jy) ? 30 : 29;
  }

  static bool _isJalaliLeap(int jy) {
    final r = jy % 33;
    return r == 1 ||
        r == 5 ||
        r == 9 ||
        r == 13 ||
        r == 17 ||
        r == 22 ||
        r == 26 ||
        r == 30;
  }

  static List<int> jalaliToGregorian(int jy, int jm, int jd) {
    var days = -355668 +
        (365 * (jy + 1595)) +
        ((jy + 1595) ~/ 33 * 8) +
        (((jy + 1595) % 33 + 3) ~/ 4) +
        jd +
        (jm < 7 ? (jm - 1) * 31 : ((jm - 7) * 30) + 186);
    var gy = 400 * (days ~/ 146097);
    days %= 146097;
    if (days > 36524) {
      gy += 100 * (--days ~/ 36524);
      days %= 36524;
      if (days >= 365) days++;
    }
    gy += 4 * (days ~/ 1461);
    days %= 1461;
    if (days > 365) {
      gy += (days - 1) ~/ 365;
      days = (days - 1) % 365;
    }
    var gd = days + 1;
    const salA = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    var gm = 0;
    for (gm = 1; gm <= 12; gm++) {
      final leap = gm == 2 && _isGregorianLeap(gy) ? 1 : 0;
      if (gd <= salA[gm] + leap) break;
      gd -= salA[gm] + leap;
    }
    return [gy, gm, gd];
  }

  static List<int> gregorianToJalali(int gy, int gm, int gd) {
    var gdm = gd;
    final gy2 = gm > 2 ? gy + 1 : gy;
    var days = 355666 +
        (365 * gy) +
        ((gy2 + 3) / 4).floor() -
        ((gy2 + 99) / 100).floor() +
        ((gy2 + 399) / 400).floor() +
        gd +
        [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334][gm - 1];
    var jy = -1595 + 33 * (days / 12053).floor();
    days %= 12053;
    jy += 4 * (days / 1461).floor();
    days %= 1461;
    if (days > 365) {
      jy += ((days - 1) / 365).floor();
      days = (days - 1) % 365;
    }
    var jm = days < 186 ? 1 + (days / 31).floor() : 7 + ((days - 186) / 30).floor();
    var jd = 1 + (days < 186 ? days % 31 : (days - 186) % 30);
    return [jy, jm, jd];
  }

  static bool _isGregorianLeap(int y) =>
      (y % 4 == 0 && y % 100 != 0) || y % 400 == 0;

  // --- Hijri (tabular Islamic calendar) ---

  static int _hijriMonthLength(int hy, int hm) {
    if (hm == 12 && _isHijriLeap(hy)) return 30;
    return hm % 2 == 1 ? 30 : 29;
  }

  static bool _isHijriLeap(int hy) => (11 * hy + 14) % 30 < 11;

  static int _hijriToJdn(int hy, int hm, int hd) {
    return hd +
        ((hm - 1) * 29.5).ceil() +
        (hy - 1) * 354 +
        ((3 + 11 * hy) / 30).floor() +
        1948439 -
        385;
  }

  static List<int> _jdnToGregorian(int jdn) {
    var l = jdn + 68569;
    final n = (4 * l / 146097).floor();
    l -= (146097 * n + 3) ~/ 4;
    final i = (4000 * (l + 1) / 1461001).floor();
    l = l - (1461 * i / 4).floor() + 31;
    final j = (80 * l / 2447).floor();
    final gd = l - (2447 * j / 80).floor();
    l = (j / 11).floor();
    final gm = j + 2 - 12 * l;
    final gy = 100 * (n - 49) + i + l;
    return [gy, gm, gd];
  }

  static List<int> hijriToGregorian(int hy, int hm, int hd) {
    return _jdnToGregorian(_hijriToJdn(hy, hm, hd));
  }

  static List<int> gregorianToHijri(int gy, int gm, int gd) {
    final jdn = _gregorianToJdn(gy, gm, gd);
    final l = jdn - 1948440 + 10632;
    final n = ((l - 1) / 10631).floor();
    final l2 = l - 10631 * n + 354;
    final j =
        ((10985 - l2) / 5316).floor() * ((50 * l2) / 17719).floor() +
            (l2 / 5670).floor() * ((43 * l2) / 15238).floor();
    final l3 = l2 -
        ((30 - j) / 15).floor() * ((17719 * j) / 50).floor() -
        (j / 16).floor() * ((15238 * j) / 43).floor() +
        29;
    final hm = ((24 * l3) / 709).floor();
    final hd = l3 - ((709 * hm) / 24).floor();
    final hy = 30 * n + j - 30;
    return [hy, hm, hd];
  }

  static int _gregorianToJdn(int gy, int gm, int gd) {
    final a = ((14 - gm) / 12).floor();
    final y = gy + 4800 - a;
    final m = gm + 12 * a - 3;
    return gd +
        ((153 * m + 2) / 5).floor() +
        365 * y +
        (y / 4).floor() -
        (y / 100).floor() +
        (y / 400).floor() -
        32045;
  }
}
