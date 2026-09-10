/// Compact local dial-code model for A2 phone entry.
///
/// Country dial code is independent of UI language. Output is canonical
/// E.164-like: `+<countrycode><national-number>` with formatting stripped.
class A2CountryDialCode {
  final String iso2;
  final String dial; // digits only, no '+'
  final String label;

  const A2CountryDialCode({
    required this.iso2,
    required this.dial,
    required this.label,
  });

  String get displayDial => '+$dial';

  @override
  bool operator ==(Object other) =>
      other is A2CountryDialCode && other.iso2 == iso2 && other.dial == dial;

  @override
  int get hashCode => Object.hash(iso2, dial);
}

class A2PhoneE164 {
  A2PhoneE164._();

  /// Curated local list — no external dependency.
  static const List<A2CountryDialCode> dialCodes = [
    A2CountryDialCode(iso2: 'IR', dial: '98', label: 'Iran'),
    A2CountryDialCode(iso2: 'US', dial: '1', label: 'United States'),
    A2CountryDialCode(iso2: 'GB', dial: '44', label: 'United Kingdom'),
    A2CountryDialCode(iso2: 'AE', dial: '971', label: 'UAE'),
    A2CountryDialCode(iso2: 'SA', dial: '966', label: 'Saudi Arabia'),
    A2CountryDialCode(iso2: 'TR', dial: '90', label: 'Turkey'),
    A2CountryDialCode(iso2: 'DE', dial: '49', label: 'Germany'),
    A2CountryDialCode(iso2: 'FR', dial: '33', label: 'France'),
    A2CountryDialCode(iso2: 'IQ', dial: '964', label: 'Iraq'),
    A2CountryDialCode(iso2: 'AF', dial: '93', label: 'Afghanistan'),
  ];

  static A2CountryDialCode get defaultDialCode => dialCodes.first;

  static A2CountryDialCode byIso2(String iso2) {
    final upper = iso2.toUpperCase();
    return dialCodes.firstWhere(
      (c) => c.iso2 == upper,
      orElse: () => defaultDialCode,
    );
  }

  static A2CountryDialCode byDial(String dial) {
    final digits = dial.replaceAll(RegExp(r'[^\d]'), '');
    return dialCodes.firstWhere(
      (c) => c.dial == digits,
      orElse: () => defaultDialCode,
    );
  }

  /// Strip UI formatting (spaces, hyphens, parentheses).
  static String stripFormatting(String input) {
    return input.trim().replaceAll(RegExp(r'[\s\-()]'), '');
  }

  /// Normalize to E.164-like using an explicit dial code.
  ///
  /// - Already-E.164 (`+...`) is accepted as-is after stripping.
  /// - Iranian compatibility: `09xxxxxxxxx` / `9xxxxxxxxx` with IR dial.
  /// - Leading national trunk `0` after dial code is stripped.
  /// - Never duplicates `+`.
  static String normalize({
    required String nationalInput,
    required A2CountryDialCode dialCode,
  }) {
    final raw = stripFormatting(nationalInput);
    if (raw.isEmpty) return '';

    if (raw.startsWith('+')) {
      return _canonicalizePlus(raw);
    }

    var national = raw.replaceAll(RegExp(r'[^\d]'), '');
    if (national.isEmpty) return '';

    // Iranian local forms when IR is selected.
    if (dialCode.dial == '98') {
      if (national.startsWith('98') && national.length >= 12) {
        return _canonicalizePlus('+$national');
      }
      if (national.startsWith('0') && national.length == 11) {
        national = national.substring(1);
      }
    } else if (national.startsWith('0')) {
      national = national.substring(1);
    }

    // Avoid duplicating dial digits if user typed them into the national field.
    if (national.startsWith(dialCode.dial) &&
        national.length > dialCode.dial.length + 4) {
      national = national.substring(dialCode.dial.length);
      if (national.startsWith('0')) {
        national = national.substring(1);
      }
    }

    return '+${dialCode.dial}$national';
  }

  static String _canonicalizePlus(String plusValue) {
    final digits = plusValue.substring(1).replaceAll(RegExp(r'[^\d]'), '');
    if (digits.isEmpty) return '';
    // Strip trunk zero immediately after country code for known codes.
    for (final code in dialCodes) {
      if (digits.startsWith(code.dial)) {
        var rest = digits.substring(code.dial.length);
        if (rest.startsWith('0')) {
          rest = rest.substring(1);
        }
        return '+${code.dial}$rest';
      }
    }
    return '+$digits';
  }

  /// Validity for A2 send CTA.
  static bool isValid({
    required String nationalInput,
    required A2CountryDialCode dialCode,
  }) {
    final e164 = normalize(
      nationalInput: nationalInput,
      dialCode: dialCode,
    );
    if (e164.isEmpty || !e164.startsWith('+')) return false;
    if (dialCode.dial == '98') {
      return RegExp(r'^\+98\d{10}$').hasMatch(e164);
    }
    // Non-IR: at least 8 digits total after '+', national portion non-empty.
    final digits = e164.substring(1);
    return digits.length >= 8 &&
        digits.length <= 15 &&
        digits.startsWith(dialCode.dial) &&
        digits.length > dialCode.dial.length;
  }

  /// Display helper for locked verified phone (IR local 0-prefix preference).
  static String formatForDisplay(String e164) {
    final cleaned = stripFormatting(e164);
    if (cleaned.startsWith('+98') && cleaned.length == 13) {
      return '0${cleaned.substring(3)}';
    }
    return cleaned;
  }
}
