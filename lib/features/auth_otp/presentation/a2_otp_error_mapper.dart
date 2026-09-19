import 'otp_login_localization.dart';

/// Code-first OTP / auth error mapping for A2 (en/fa/ar via [OtpLoginLocalization]).
///
/// Message-text heuristics are fallback only. Does not invent clinical meanings.
class A2OtpErrorMapper {
  A2OtpErrorMapper._();

  static String mapRequest({
    required OtpLoginLocalization l10n,
    String? code,
    String? message,
    int? statusCode,
  }) {
    final byCode = _mapKnownCode(l10n: l10n, code: code, isRequest: true);
    if (byCode != null) return byCode;

    final msg = message ?? '';
    if (statusCode == 503) return l10n.serverUnavailable;
    if (_looksLikeNetwork(msg)) return l10n.networkError;
    if (_looksLikeTooMany(msg) || code == 'TOO_MANY_ATTEMPTS') {
      return l10n.tooManyOtp;
    }
    if (statusCode != null && statusCode >= 500) {
      return l10n.serverUnavailable;
    }
    return l10n.genericOtpRequestFailed;
  }

  static String mapVerify({
    required OtpLoginLocalization l10n,
    String? code,
    String? message,
    int? statusCode,
  }) {
    final byCode = _mapKnownCode(l10n: l10n, code: code, isRequest: false);
    if (byCode != null) return byCode;

    final msg = message ?? '';
    if (_looksLikeNetwork(msg)) return l10n.networkError;
    if (_looksLikeTooMany(msg)) return l10n.tooManyOtp;
    if (msg.toLowerCase().contains('expired')) return l10n.otpExpired;
    if (msg.toLowerCase().contains('invalid')) return l10n.otpInvalid;
    return l10n.genericOtpVerifyFailed;
  }

  static String? _mapKnownCode({
    required OtpLoginLocalization l10n,
    required String? code,
    required bool isRequest,
  }) {
    if (code == null || code.trim().isEmpty) return null;
    switch (code.trim().toUpperCase()) {
      case 'OTP_REQUEST_FAILED':
        return l10n.genericOtpRequestFailed;
      case 'OTP_INVALID':
        return l10n.otpInvalid;
      case 'OTP_EXPIRED':
        return l10n.otpExpired;
      case 'TOO_MANY_ATTEMPTS':
        return l10n.tooManyOtp;
      case 'ACCOUNT_NOT_FOUND':
        return l10n.accountNotFoundCreateAccount;
      case 'ACCOUNT_EXISTS':
        return l10n.accountExistsHaveAccount;
      default:
        if (isRequest && code.toUpperCase().contains('OTP_REQUEST')) {
          return l10n.genericOtpRequestFailed;
        }
        return null;
    }
  }

  static bool _looksLikeNetwork(String message) {
    final m = message.toLowerCase();
    return m.contains('timeout') ||
        m.contains('socket') ||
        m.contains('failed host lookup') ||
        m.contains('connection');
  }

  static bool _looksLikeTooMany(String message) {
    return message.contains('Too many OTP') ||
        message.toLowerCase().contains('too many');
  }
}
