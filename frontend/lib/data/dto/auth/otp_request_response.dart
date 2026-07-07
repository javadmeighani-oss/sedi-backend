import '../../../core/network/api_error.dart';
import '../../../core/network/api_response.dart';

/// Gate 2 OTP request outcome derived from the backend V1 envelope.
/// See: frontend/docs/FRONTEND_BACKEND_ALIGNMENT.md (OTP Auth / Stage 25).
class OtpRequestResult {
  final bool isSuccess;
  final ApiResponse<Map<String, dynamic>> response;

  const OtpRequestResult({
    required this.isSuccess,
    required this.response,
  });

  factory OtpRequestResult.fromApiResponse(
    ApiResponse<Map<String, dynamic>> response,
  ) {
    return OtpRequestResult(
      isSuccess: _evaluateSuccess(response),
      response: response,
    );
  }

  int? get statusCode => response.statusCode;
  ApiError? get error => response.error;
  String get errorMessage => response.errorMessage;

  static bool _evaluateSuccess(ApiResponse<Map<String, dynamic>> response) {
    final status = response.statusCode;
    if (status != null && (status < 200 || status >= 300)) {
      return false;
    }

    if (response.ok) {
      return true;
    }

    if (response.error != null) {
      return false;
    }

    return _hasOtpSuccessPayload(response.data);
  }

  static bool _hasOtpSuccessPayload(Map<String, dynamic>? data) {
    if (data == null) return false;
    if (data['next'] != 'verify_otp') return false;

    final nestedOk = data['ok'];
    if (nestedOk is bool) return nestedOk;
    return true;
  }
}
