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
  final message = meRes.errorMessage.toLowerCase();
  if (code == 'PARSE_ERROR' ||
      code == 'MISSING_IDENTITY' ||
      code == 'ENVELOPE_ERROR' ||
      message.contains('parse') ||
      message.contains('profile data') ||
      message.contains('missing profile') ||
      message.contains('profile identity') ||
      message.contains('unrecognized /auth/me')) {
    return PostOtpMeFailureKind.parse;
  }

  return PostOtpMeFailureKind.fetch;
}

/// True when GET `/auth/me` failed for a likely transient reason (retry/fallback).
bool isTransientPostOtpMeFailure(ApiResponse<MeProfileDto> meRes) {
  if (meRes.ok) return false;
  final kind = classifyPostOtpMeFailure(meRes);
  if (kind == PostOtpMeFailureKind.auth) return false;
  final status = meRes.statusCode;
  if (status == null) return true;
  return status >= 500;
}
