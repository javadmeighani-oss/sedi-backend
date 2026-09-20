/// Pure calendar conversion math (Gregorian / Jalali / Hijri).
/// Presentation-only; ISO `YYYY-MM-DD` remains canonical.
class CalendarDateMath {
  CalendarDateMath._();

  static bool isGregorianLeap(int y) =>
      (y % 4 == 0 && y % 100 != 0) || y % 400 == 0;

  static int jalaliMonthLength(int jy, int jm) {
    if (jm <= 6) return 31;
    if (jm <= 11) return 30;
    return isJalaliLeap(jy) ? 30 : 29;
  }

  static bool isJalaliLeap(int jy) {
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
      final leap = gm == 2 && isGregorianLeap(gy) ? 1 : 0;
      if (gd <= salA[gm] + leap) break;
      gd -= salA[gm] + leap;
    }
    return [gy, gm, gd];
  }

  static List<int> gregorianToJalali(int gy, int gm, int gd) {
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
    var jm =
        days < 186 ? 1 + (days / 31).floor() : 7 + ((days - 186) / 30).floor();
    var jd = 1 + (days < 186 ? days % 31 : (days - 186) % 30);
    return [jy, jm, jd];
  }

  static int hijriMonthLength(int hy, int hm) {
    if (hm == 12 && isHijriLeap(hy)) return 30;
    return hm % 2 == 1 ? 30 : 29;
  }

  static bool isHijriLeap(int hy) => (11 * hy + 14) % 30 < 11;

  static int hijriToJdn(int hy, int hm, int hd) {
    return hd +
        ((hm - 1) * 29.5).ceil() +
        (hy - 1) * 354 +
        ((3 + 11 * hy) / 30).floor() +
        1948439 -
        385;
  }

  static List<int> jdnToGregorian(int jdn) {
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
    return jdnToGregorian(hijriToJdn(hy, hm, hd));
  }

  static int gregorianToJdn(int gy, int gm, int gd) {
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

  static List<int> gregorianToHijri(int gy, int gm, int gd) {
    final jdn = gregorianToJdn(gy, gm, gd);
    final l = jdn - 1948440 + 10632;
    final n = ((l - 1) / 10631).floor();
    final l2 = l - 10631 * n + 354;
    final j = ((10985 - l2) / 5316).floor() * ((50 * l2) / 17719).floor() +
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

  /// Parse backend ISO `YYYY-MM-DD` without device-timezone day inference.
  static DateTime? parseIsoLocalDate(String? iso) {
    if (iso == null) return null;
    final m = RegExp(r'^(\d{4})-(\d{2})-(\d{2})$').firstMatch(iso.trim());
    if (m == null) return null;
    final y = int.tryParse(m.group(1)!);
    final mo = int.tryParse(m.group(2)!);
    final d = int.tryParse(m.group(3)!);
    if (y == null || mo == null || d == null) return null;
    return DateTime.utc(y, mo, d);
  }

  /// Presentation-only calendar date for language: en=Gregorian, fa=Jalali, ar=Hijri.
  static String formatIsoForLanguage(String iso, String languageCode) {
    final dt = parseIsoLocalDate(iso);
    if (dt == null) return iso;
    final y = dt.year;
    final m = dt.month;
    final d = dt.day;
    final pad = (int n) => n.toString().padLeft(2, '0');
    switch (languageCode) {
      case 'fa':
        final j = gregorianToJalali(y, m, d);
        return '${j[0]}/${pad(j[1])}/${pad(j[2])}';
      case 'ar':
        final h = gregorianToHijri(y, m, d);
        return '${h[0]}/${pad(h[1])}/${pad(h[2])}';
      default:
        return '${y}-${pad(m)}-${pad(d)}';
    }
  }

  /// Profile DOB presentation: calendar conversion + script digits for fa/ar.
  static String formatIsoForProfileDisplay(String iso, String languageCode) {
    return localizeDigitsForLanguage(
      formatIsoForLanguage(iso, languageCode),
      languageCode,
    );
  }

  /// Latin digits → Persian (fa) or Arabic-Indic (ar). en unchanged.
  static String localizeDigitsForLanguage(String input, String languageCode) {
    if (languageCode == 'fa') {
      const map = {
        '0': '۰',
        '1': '۱',
        '2': '۲',
        '3': '۳',
        '4': '۴',
        '5': '۵',
        '6': '۶',
        '7': '۷',
        '8': '۸',
        '9': '۹',
      };
      return input.split('').map((c) => map[c] ?? c).join();
    }
    if (languageCode == 'ar') {
      const map = {
        '0': '٠',
        '1': '١',
        '2': '٢',
        '3': '٣',
        '4': '٤',
        '5': '٥',
        '6': '٦',
        '7': '٧',
        '8': '٨',
        '9': '٩',
      };
      return input.split('').map((c) => map[c] ?? c).join();
    }
    return input;
  }

  /// ISO weekday 1=Mon … 7=Sun from backend local_date (UTC date components).
  static int? weekdayFromIso(String iso) {
    final dt = parseIsoLocalDate(iso);
    return dt?.weekday;
  }
}
