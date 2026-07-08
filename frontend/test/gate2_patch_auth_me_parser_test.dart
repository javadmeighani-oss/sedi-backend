import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/data/dto/auth/auth_me_response_parser.dart';
import 'package:sedi_app/data/dto/auth/me_profile.dart';
import 'package:sedi_app/data/dto/auth/me_profile_parser.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_profile_rules.dart';

import 'fixtures/auth_me_backend_fixture.dart';

void main() {
  group('PATCH /auth/me response parsing', () {
    test('dedicated parser accepts PATCH envelope with null phone via OTP fallback', () {
      final payload = Map<String, dynamic>.from(backendAuthMeCompleteProfile)
        ..['phone'] = null;

      final result = AuthMeResponseParser.parseHttpResponse(
        statusCode: 200,
        body: jsonEncode(backendAuthMeEnvelope(payload)),
        knownPhoneE164: '+989121234567',
      );

      expect(result.ok, isTrue);
      expect(result.profile?.phone, '+989121234567');
      expect(Gate2ProfileRules.isProfileComplete(result.profile!), isTrue);
    });

    test('generic parseMeProfileDto rejects same PATCH payload without phone fallback', () {
      final payload = Map<String, dynamic>.from(backendAuthMeCompleteProfile)
        ..['phone'] = null;

      expect(parseMeProfileDto(payload), isNull);
    });

    test('PATCH response with nested data.user parses', () {
      final result = AuthMeResponseParser.parseHttpResponse(
        statusCode: 200,
        body: jsonEncode({
          'ok': true,
          'data': {
            'user': backendAuthMeCompleteProfile,
          },
          'error': null,
        }),
        knownPhoneE164: '+989121234567',
      );

      expect(result.ok, isTrue);
      expect(result.profile?.name, 'Sara');
      expect(Gate2ProfileRules.isProfileComplete(result.profile!), isTrue);
    });

    test('PATCH 422 is not treated as success', () {
      final result = AuthMeResponseParser.parseHttpResponse(
        statusCode: 422,
        body: '{"detail":[{"loc":["body","sex"],"msg":"validation error"}]}',
      );

      expect(result.ok, isFalse);
      expect(result.profile, isNull);
    });
  });
}
