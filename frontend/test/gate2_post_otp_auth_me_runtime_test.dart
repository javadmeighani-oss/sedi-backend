import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/auth/auth_profile_service.dart';
import 'package:sedi_app/core/network/api_error.dart';
import 'package:sedi_app/core/network/api_response.dart';
import 'package:sedi_app/data/dto/auth/auth_me_response_parser.dart';
import 'package:sedi_app/data/dto/auth/me_profile.dart';
import 'package:sedi_app/data/dto/auth/me_profile_parser.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_post_otp_me_failure.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_post_otp_router.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_profile_rules.dart';

import 'fixtures/auth_me_backend_fixture.dart';

void main() {
  group('Post-OTP runtime /auth/me parser', () {
    test('1. incomplete backend profile parses and routes to completion', () {
      final result = AuthMeResponseParser.parseHttpResponse(
        statusCode: 200,
        body: jsonEncode(backendAuthMeEnvelope(backendAuthMeIncompleteProfile)),
        knownPhoneE164: '+989121234567',
      );

      expect(result.ok, isTrue);
      expect(result.profile, isNotNull);
      expect(Gate2ProfileRules.isProfileComplete(result.profile!), isFalse);

      final action = Gate2PostOtpRouter.decide(
        isNewUserPath: true,
        me: result.profile!,
        registrationDraftComplete: false,
      );
      expect(action, Gate2PostOtpAction.showRegistrationCompletion);
      expect(
        classifyPostOtpMeFailure(result.toApiResponse()),
        isNot(PostOtpMeFailureKind.parse),
      );
    });

    test('2. complete profile parses, is cacheable, routes to Gate 3', () {
      final result = AuthMeResponseParser.parseHttpResponse(
        statusCode: 200,
        body: jsonEncode(backendAuthMeEnvelope(backendAuthMeCompleteProfile)),
        knownPhoneE164: '+989121234567',
      );

      expect(result.ok, isTrue);
      expect(Gate2ProfileRules.isProfileComplete(result.profile!), isTrue);

      final action = Gate2PostOtpRouter.decide(
        isNewUserPath: false,
        me: result.profile!,
        registrationDraftComplete: false,
      );
      expect(action, Gate2PostOtpAction.enterGate3);

      final cached = AuthProfileService.toUserProfile(result.profile!);
      expect(cached.isVerified, isTrue);
      expect(cached.userId, 42);
    });

    test('3. dedicated parser extracts envelope.data; generic path uses data only', () {
      final envelope = backendAuthMeEnvelope(backendAuthMeIncompleteProfile);
      final extracted = AuthMeResponseParser.extractDataPayload(envelope);
      expect(extracted, isNotNull);
      expect(extracted!['user_id'], 42);

      final dedicated = AuthMeResponseParser.parseHttpResponse(
        statusCode: 200,
        body: jsonEncode(envelope),
        knownPhoneE164: '+989121234567',
      );
      expect(dedicated.ok, isTrue);

      final generic = ApiResponse.fromJson<MeProfileDto>(
        envelope,
        parseMeProfileDto,
      );
      expect(generic.ok, isTrue);
      expect(generic.data?.userId, 42);
    });

    test('4. ok:true with unparseable data is PARSE_ERROR and not success', () {
      final result = AuthMeResponseParser.parseHttpResponse(
        statusCode: 200,
        body: jsonEncode({
          'ok': true,
          'data': 'not-a-map',
          'error': null,
        }),
        knownPhoneE164: '+989121234567',
      );

      expect(result.ok, isFalse);
      expect(result.profile, isNull);
      expect(result.error?.code, 'PARSE_ERROR');
      expect(
        classifyPostOtpMeFailure(result.toApiResponse()),
        PostOtpMeFailureKind.parse,
      );
    });

    test('5. missing required identity is parse failure', () {
      final missingUser = AuthMeResponseParser.parseHttpResponse(
        statusCode: 200,
        body: jsonEncode({
          'ok': true,
          'data': {'phone': '+989121234567'},
          'error': null,
        }),
      );
      expect(missingUser.ok, isFalse);
      expect(missingUser.failureKind, AuthMeFailureKind.missingIdentity);

      final missingPhone = AuthMeResponseParser.parseHttpResponse(
        statusCode: 200,
        body: jsonEncode({
          'ok': true,
          'data': {'user_id': 42},
          'error': null,
        }),
      );
      expect(missingPhone.ok, isFalse);
      expect(missingPhone.failureKind, AuthMeFailureKind.missingIdentity);
    });

    test('6. incomplete optional profile parses with null phone via OTP fallback', () {
      final payload = Map<String, dynamic>.from(backendAuthMeIncompleteProfile)
        ..['phone'] = null;

      final result = AuthMeResponseParser.parseHttpResponse(
        statusCode: 200,
        body: jsonEncode(backendAuthMeEnvelope(payload)),
        knownPhoneE164: '+989121234567',
      );

      expect(result.ok, isTrue);
      expect(result.profile?.phone, '+989121234567');
      expect(Gate2ProfileRules.isProfileComplete(result.profile!), isFalse);

      final returning = Gate2PostOtpRouter.decide(
        isNewUserPath: false,
        me: result.profile!,
        registrationDraftComplete: false,
      );
      expect(returning, Gate2PostOtpAction.showProfileCorrectionReturning);
    });

    test('7. 401/403 shows auth failure not parse failure', () {
      for (final status in [401, 403]) {
        final result = AuthMeResponseParser.parseHttpResponse(
          statusCode: status,
          body: '{"detail":"Unauthorized"}',
        );
        expect(result.failureKind, AuthMeFailureKind.authError);
        expect(
          classifyPostOtpMeFailure(result.toApiResponse()),
          PostOtpMeFailureKind.auth,
        );
      }
    });

    test('8. 5xx/network-style failures show fetch failure not parse failure', () {
      final serverError = AuthMeResponseParser.parseHttpResponse(
        statusCode: 500,
        body: '{"ok":false,"error":{"code":"INTERNAL","message":"Server error"}}',
      );
      expect(serverError.failureKind, AuthMeFailureKind.fetchError);
      expect(
        classifyPostOtpMeFailure(serverError.toApiResponse()),
        PostOtpMeFailureKind.fetch,
      );

      final network = ApiResponse<MeProfileDto>(
        ok: false,
        error: ApiError(code: 'NETWORK_ERROR', message: 'SocketException'),
      );
      expect(
        classifyPostOtpMeFailure(network),
        PostOtpMeFailureKind.fetch,
      );
    });
  });

  group('PR #44 regression reproduction', () {
    test('generic parseMeProfileDto rejects null phone without OTP fallback', () {
      final payload = Map<String, dynamic>.from(backendAuthMeIncompleteProfile)
        ..['phone'] = null;

      expect(parseMeProfileDto(payload), isNull);
    });

    test('dedicated post-OTP parser accepts same payload with known phone', () {
      final payload = Map<String, dynamic>.from(backendAuthMeIncompleteProfile)
        ..['phone'] = null;

      final result = AuthMeResponseParser.parseHttpResponse(
        statusCode: 200,
        body: jsonEncode(backendAuthMeEnvelope(payload)),
        knownPhoneE164: '+989121234567',
      );
      expect(result.ok, isTrue);
      expect(result.profile?.phone, '+989121234567');
    });
  });
}
