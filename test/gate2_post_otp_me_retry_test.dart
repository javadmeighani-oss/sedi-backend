import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/network/api_error.dart';
import 'package:sedi_app/core/network/api_response.dart';
import 'package:sedi_app/data/dto/auth/me_profile.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_post_otp_me_failure.dart';

void main() {
  group('fetchMeAfterOtp transient retry eligibility', () {
    test('503 and network errors are transient', () {
      final serverBusy = ApiResponse<MeProfileDto>(
        ok: false,
        error: ApiError(code: 'HTTP_503', message: 'Server busy'),
        statusCode: 503,
      );
      expect(isTransientPostOtpMeFailure(serverBusy), isTrue);

      final network = ApiResponse<MeProfileDto>(
        ok: false,
        error: ApiError(code: 'NETWORK_ERROR', message: 'SocketException'),
      );
      expect(isTransientPostOtpMeFailure(network), isTrue);
    });

    test('401/403 and parse errors are not transient', () {
      final auth = ApiResponse<MeProfileDto>(
        ok: false,
        error: ApiError(code: 'AUTH_ERROR', message: 'Authentication failed'),
        statusCode: 401,
      );
      expect(isTransientPostOtpMeFailure(auth), isFalse);
      expect(classifyPostOtpMeFailure(auth), PostOtpMeFailureKind.auth);

      final parse = ApiResponse<MeProfileDto>(
        ok: false,
        error: ApiError(code: 'PARSE_ERROR', message: 'Missing profile data'),
        statusCode: 200,
      );
      expect(isTransientPostOtpMeFailure(parse), isFalse);
      expect(classifyPostOtpMeFailure(parse), PostOtpMeFailureKind.parse);
    });

    test('successful response is not transient', () {
      const success = ApiResponse<MeProfileDto>(
        ok: true,
        data: MeProfileDto(userId: 1, phone: '+989121234567'),
        statusCode: 200,
      );
      expect(isTransientPostOtpMeFailure(success), isFalse);
    });
  });
}
