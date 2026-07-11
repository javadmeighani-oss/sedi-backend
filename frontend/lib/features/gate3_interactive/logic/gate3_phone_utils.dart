class Gate3PhoneUtils {
  Gate3PhoneUtils._();

  static String normalize(String input) {
    var s = input.trim().replaceAll(' ', '').replaceAll('-', '');
    if (s.startsWith('+')) return s;
    if (s.startsWith('0') && s.length == 11) return '+98${s.substring(1)}';
    if (s.startsWith('9') && s.length == 10) return '+98$s';
    if (s.startsWith('98') && s.length == 12) return '+$s';
    return s;
  }

  static bool isValid(String input) {
    final normalized = normalize(input);
    if (normalized.startsWith('+98')) {
      return RegExp(r'^\+98\d{10}$').hasMatch(normalized);
    }
    return normalized.length >= 8;
  }
}
