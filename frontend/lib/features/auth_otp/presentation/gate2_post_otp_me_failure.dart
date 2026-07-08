import '../../../core/network/api_response.dart';
import '../../../data/dto/auth/me_profile.dart';

/// UI-facing failure kinds for post-OTP GET `/auth/me`.
enum PostOtpMeFailureKind {
  auth,
  parse,
  fetch,
}

/// Classifies post-OTP `/auth/me` failures for snackbar messaging.
PostOtpMeFailureKind classifyPostOtpMeFailure(ApiResponse<MeProfileDto> meRes) {
  final status = meRes.statusCode;
  if (status == 401 ||
      status == 403 ||
      meRes.error?.code == 'AUTH_ERROR') {
    return PostOtpMeFailureKind.auth;
  }

  final code = meRes.error?.code;
  if (code == 'PARSE_ERROR' ||
      code == 'MISSING_IDENTITY' ||
      meRes.errorMessage.toLowerCase().contains('parse') ||
      meRes.errorMessage.toLowerCase().contains('profile data') ||
      meRes.errorMessage.toLowerCase().contains('missing profile')) {
    return PostOtpMeFailureKind.parse;
  }

  return PostOtpMeFailureKind.fetch;
}
