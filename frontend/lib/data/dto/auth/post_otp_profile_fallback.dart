import 'me_profile.dart';
import 'otp_verify_response.dart';

/// Builds a minimal identity-only draft from OTP verify when GET `/auth/me` fails.
///
/// This is not backend-confirmed and must not be cached or used to enter Gate 3.
MeProfileDto? postOtpProfileFromVerify(
  OtpVerifyResponse verify, {
  String? fallbackPhoneE164,
}) {
  final userId = verify.userId;
  if (userId == null || userId <= 0) return null;

  final phone = _firstNonEmptyPhone(verify.phone, fallbackPhoneE164);
  if (phone == null) return null;

  return MeProfileDto(
    userId: userId,
    phone: phone,
    name: verify.name,
    preferredLanguage: verify.language,
    sex: verify.sex,
    dateOfBirth: verify.dateOfBirth,
  );
}

String? _firstNonEmptyPhone(String? primary, String? fallback) {
  for (final candidate in [primary, fallback]) {
    final trimmed = candidate?.trim();
    if (trimmed != null && trimmed.isNotEmpty) return trimmed;
  }
  return null;
}
