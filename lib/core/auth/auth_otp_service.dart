import '../../data/dto/auth/me_profile.dart';
import '../../data/dto/auth/otp_request.dart';
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
    required OtpPurpose purpose,
    String? language,
  }) async {
    final dto = OtpRequestDto(phone: phone, purpose: purpose);
    final headers = <String, String>{};
    if (language != null && language.trim().isNotEmpty) {
      headers['Accept-Language'] = language.trim();
    }

    return _apiClient.postRaw(
      '/auth/otp/request',
      body: dto.toJson(),
      extraHeaders: headers.isEmpty ? null : headers,
    );
  }

  /// Verify OTP and return tokens. Profile sync is handled separately via [AuthProfileService].
  Future<ApiResponse<OtpVerifyResponse>> verifyOtp({
    required String phone,
    required String code,
    required OtpPurpose purpose,
    String? language,
  }) async {
    final dto = OtpVerifyDto(phone: phone, code: code, purpose: purpose);
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

  /// Authenticated A3 phone-change: OTP to NEW E.164 (JWT account authority).
  Future<ApiResponse<Map<String, dynamic>>> requestPhoneChangeOtp({
    required String newPhone,
    String? language,
  }) async {
    final headers = <String, String>{};
    if (language != null && language.trim().isNotEmpty) {
      headers['Accept-Language'] = language.trim();
    }
    return _apiClient.postRaw(
      '/auth/phone-change/request',
      body: {'new_phone': newPhone},
      extraHeaders: headers.isEmpty ? null : headers,
    );
  }

  /// Verify phone-change OTP; response data is refreshed /auth/me profile.
  Future<ApiResponse<MeProfileDto>> verifyPhoneChangeOtp({
    required String newPhone,
    required String code,
  }) async {
    return _apiClient.post<MeProfileDto>(
      '/auth/phone-change/verify',
      body: {'new_phone': newPhone, 'code': code},
      parser: (json) {
        if (json is Map) {
          return MeProfileDto.fromJson(Map<String, dynamic>.from(json));
        }
        return null;
      },
    );
  }
}
