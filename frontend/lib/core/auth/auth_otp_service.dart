import '../../data/dto/auth/otp_request.dart';
import '../../data/dto/auth/otp_request_response.dart';
import '../../data/dto/auth/otp_verify.dart';
import '../../data/dto/auth/otp_verify_response.dart';
import '../network/api_client.dart';
import '../network/api_response.dart';

class AuthOtpService {
  final ApiClient _apiClient;

  AuthOtpService({ApiClient? apiClient})
      : _apiClient = apiClient ?? ApiClient(timeout: const Duration(seconds: 30));

  Future<ApiResponse<Map<String, dynamic>>> requestOtp({
    required String phone,
    String? language,
  }) async {
    final result = await requestOtpResult(phone: phone, language: language);
    return result.response;
  }

  /// OTP request with explicit success evaluation for Gate 2 navigation.
  Future<OtpRequestResult> requestOtpResult({
    required String phone,
    String? language,
  }) async {
    final dto = OtpRequestDto(phone: phone);
    final headers = <String, String>{};
    if (language != null && language.trim().isNotEmpty) {
      headers['Accept-Language'] = language.trim();
    }

    final response = await _apiClient.postRaw(
      '/auth/otp/request',
      body: dto.toJson(),
      extraHeaders: headers.isEmpty ? null : headers,
    );
    return OtpRequestResult.fromApiResponse(response);
  }

  /// Verify OTP and return tokens. Profile sync is handled separately via [AuthProfileService].
  Future<ApiResponse<OtpVerifyResponse>> verifyOtp({
    required String phone,
    required String code,
    String? language,
  }) async {
    final dto = OtpVerifyDto(phone: phone, code: code);
    final headers = <String, String>{};
    if (language != null && language.trim().isNotEmpty) {
      headers['Accept-Language'] = language.trim();
    }

    return _apiClient.post<OtpVerifyResponse>(
      '/auth/otp/verify',
      body: dto.toJson(),
      extraHeaders: headers.isEmpty ? null : headers,
      parser: (json) {
        if (json is Map) {
          return OtpVerifyResponse.fromJson(Map<String, dynamic>.from(json));
        }
        return null;
      },
    );
  }
}
