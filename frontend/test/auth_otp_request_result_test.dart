import 'package:flutter_test/flutter_test.dart';

import 'package:sedi_app/core/network/api_error.dart';
import 'package:sedi_app/core/network/api_response.dart';
import 'package:sedi_app/data/dto/auth/otp_request_response.dart';

void main() {
  group('OtpRequestResult', () {
    test('success with top-level ok true and verify_otp payload', () {
      final response = ApiResponse<Map<String, dynamic>>(
        ok: true,
        statusCode: 200,
        data: const {'ok': true, 'next': 'verify_otp'},
      );

      final result = OtpRequestResult.fromApiResponse(response);
      expect(result.isSuccess, isTrue);
    });

    test('success with nested payload when top-level ok missing in envelope', () {
      final response = ApiResponse<Map<String, dynamic>>(
        ok: false,
        statusCode: 200,
        data: const {'ok': true, 'next': 'verify_otp'},
      );

      final result = OtpRequestResult.fromApiResponse(response);
      expect(result.isSuccess, isTrue);
    });

    test('success with next verify_otp when nested ok omitted', () {
      final response = ApiResponse<Map<String, dynamic>>(
        ok: true,
        statusCode: 200,
        data: const {'next': 'verify_otp'},
      );

      final result = OtpRequestResult.fromApiResponse(response);
      expect(result.isSuccess, isTrue);
    });

    test('failure with OTP_REQUEST_FAILED and no success payload', () {
      final response = ApiResponse<Map<String, dynamic>>(
        ok: false,
        statusCode: 200,
        error: const ApiError(
          code: 'OTP_REQUEST_FAILED',
          message: 'SMS delivery failed',
        ),
      );

      final result = OtpRequestResult.fromApiResponse(response);
      expect(result.isSuccess, isFalse);
    });

    test('failure with rate limit message', () {
      final response = ApiResponse<Map<String, dynamic>>(
        ok: false,
        statusCode: 200,
        error: const ApiError(
          code: 'OTP_REQUEST_FAILED',
          message: 'Too many OTP requests. Try again later.',
        ),
      );

      final result = OtpRequestResult.fromApiResponse(response);
      expect(result.isSuccess, isFalse);
    });

    test('failure with HTTP 503', () {
      final response = ApiResponse<Map<String, dynamic>>(
        ok: false,
        statusCode: 503,
        error: const ApiError(
          code: 'HTTP_503',
          message: 'Service unavailable',
        ),
      );

      final result = OtpRequestResult.fromApiResponse(response);
      expect(result.isSuccess, isFalse);
    });

    test('failure when nested ok is false', () {
      final response = ApiResponse<Map<String, dynamic>>(
        ok: false,
        statusCode: 200,
        data: const {'ok': false, 'next': 'verify_otp'},
      );

      final result = OtpRequestResult.fromApiResponse(response);
      expect(result.isSuccess, isFalse);
    });
  });

  group('ApiResponse.fromJson ok parsing', () {
    test('parses string ok true', () {
      final response = ApiResponse.fromJson<Map<String, dynamic>>(
        {
          'ok': 'true',
          'data': {'next': 'verify_otp'},
          'error': null,
        },
        (v) => v == null ? null : Map<String, dynamic>.from(v as Map),
      );

      expect(response.ok, isTrue);
    });
  });
}
