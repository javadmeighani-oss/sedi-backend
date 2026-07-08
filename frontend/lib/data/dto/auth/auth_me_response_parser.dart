import 'dart:convert';

import 'package:flutter/foundation.dart';

import '../../../core/network/api_error.dart';
import '../../../core/network/api_response.dart';
import 'me_profile.dart';
import 'me_profile_parser.dart';

/// Failure kinds for GET `/auth/me` during Gate 2 post-OTP routing.
enum AuthMeFailureKind {
  invalidJson,
  envelopeRejected,
  missingData,
  parseError,
  missingIdentity,
  authError,
  fetchError,
}

/// Parsed GET `/auth/me` HTTP response for Gate 2 post-OTP flow.
class AuthMeFetchResult {
  final bool ok;
  final MeProfileDto? profile;
  final AuthMeFailureKind? failureKind;
  final ApiError? error;
  final int? statusCode;

  const AuthMeFetchResult({
    required this.ok,
    this.profile,
    this.failureKind,
    this.error,
    this.statusCode,
  });

  ApiResponse<MeProfileDto> toApiResponse() {
    return ApiResponse<MeProfileDto>(
      ok: ok,
      data: profile,
      error: error,
      statusCode: statusCode,
    );
  }
}

/// Endpoint-specific parser for GET `/auth/me` (not generic ApiResponse heuristics).
class AuthMeResponseParser {
  AuthMeResponseParser._();

  /// Parse raw HTTP response from GET `/auth/me`.
  ///
  /// [knownPhoneE164] may be supplied after OTP verify when the backend profile
  /// omits `phone` but identity was already confirmed by OTP.
  static AuthMeFetchResult parseHttpResponse({
    required int statusCode,
    required String body,
    String? knownPhoneE164,
  }) {
    if (statusCode == 401 || statusCode == 403) {
      return AuthMeFetchResult(
        ok: false,
        failureKind: AuthMeFailureKind.authError,
        error: ApiError(
          code: 'AUTH_ERROR',
          message: 'Authentication failed',
        ),
        statusCode: statusCode,
      );
    }

    if (statusCode < 200 || statusCode >= 300) {
      return AuthMeFetchResult(
        ok: false,
        failureKind: AuthMeFailureKind.fetchError,
        error: ApiError(
          code: 'HTTP_$statusCode',
          message: 'Request failed with status $statusCode',
        ),
        statusCode: statusCode,
      );
    }

    final Map<String, dynamic>? envelope = _decodeJsonObject(body);
    if (envelope == null) {
      _logDebug('invalid_json', keys: const []);
      return AuthMeFetchResult(
        ok: false,
        failureKind: AuthMeFailureKind.invalidJson,
        error: const ApiError(
          code: 'PARSE_ERROR',
          message: 'Invalid JSON response',
        ),
        statusCode: statusCode,
      );
    }

    _logDebug('envelope_keys', keys: envelope.keys.map((k) => k.toString()).toList());

    if (_isEnvelopeShape(envelope)) {
      final parsedOk = ApiResponse.readEnvelopeOk(envelope['ok']);
      final errorJson = envelope['error'];
      if (errorJson is Map && errorJson.isNotEmpty) {
        final apiError = ApiError.fromJson(Map<String, dynamic>.from(errorJson));
        _logDebug('envelope_error', keys: [apiError.code ?? 'unknown']);
        return AuthMeFetchResult(
          ok: false,
          failureKind: AuthMeFailureKind.envelopeRejected,
          error: apiError,
          statusCode: statusCode,
        );
      }
      if (!parsedOk) {
        _logDebug('envelope_ok_false', keys: const []);
        return AuthMeFetchResult(
          ok: false,
          failureKind: AuthMeFailureKind.envelopeRejected,
          error: const ApiError(
            code: 'ENVELOPE_ERROR',
            message: 'Backend returned ok=false',
          ),
          statusCode: statusCode,
        );
      }

      final dataMap = extractDataPayload(envelope);
      if (dataMap == null) {
        _logDebug('missing_data', keys: const []);
        return AuthMeFetchResult(
          ok: false,
          failureKind: AuthMeFailureKind.missingData,
          error: const ApiError(
            code: 'PARSE_ERROR',
            message: 'Missing profile data in response',
          ),
          statusCode: statusCode,
        );
      }

      _logDebug('data_keys', keys: dataMap.keys.map((k) => k.toString()).toList());
      return _parseProfileMap(
        dataMap,
        knownPhoneE164: knownPhoneE164,
        statusCode: statusCode,
      );
    }

    if (_looksLikeProfileMap(envelope)) {
      _logDebug('flat_profile_body', keys: envelope.keys.map((k) => k.toString()).toList());
      return _parseProfileMap(
        envelope,
        knownPhoneE164: knownPhoneE164,
        statusCode: statusCode,
      );
    }

    _logDebug('unrecognized_body', keys: envelope.keys.map((k) => k.toString()).toList());
    return AuthMeFetchResult(
      ok: false,
      failureKind: AuthMeFailureKind.parseError,
      error: const ApiError(
        code: 'PARSE_ERROR',
        message: 'Unrecognized /auth/me response shape',
      ),
      statusCode: statusCode,
    );
  }

  /// Extract the profile map from a backend envelope or nested `data` wrappers.
  @visibleForTesting
  static Map<String, dynamic>? extractDataPayload(Map<String, dynamic> envelope) {
    Object? current = envelope['data'];
    if (current == null && _looksLikeProfileMap(envelope)) {
      return _profileOnlyMap(envelope);
    }

    for (var depth = 0; depth < 4; depth++) {
      final map = _coerceToMap(current);
      if (map == null) return null;

      if (_looksLikeProfileMap(map)) {
        return _profileOnlyMap(map);
      }

      for (final key in const ['user', 'profile', 'me']) {
        final nested = _coerceToMap(map[key]);
        if (nested != null && _looksLikeProfileMap(nested)) {
          return _profileOnlyMap(nested);
        }
      }

      if (map.containsKey('data')) {
        current = map['data'];
        continue;
      }
      return null;
    }
    return null;
  }

  static AuthMeFetchResult _parseProfileMap(
    Map<String, dynamic> dataMap, {
    required int statusCode,
    String? knownPhoneE164,
  }) {
    if (_isEnvelopeShape(dataMap)) {
      _logDebug('wrong_layer_envelope_in_data', keys: dataMap.keys.map((k) => k.toString()).toList());
      return AuthMeFetchResult(
        ok: false,
        failureKind: AuthMeFailureKind.parseError,
        error: const ApiError(
          code: 'PARSE_ERROR',
          message: 'Profile parser received envelope instead of data',
        ),
        statusCode: statusCode,
      );
    }

    try {
      final profile = MeProfileDto.fromJson(dataMap);
      final resolved = resolvePostOtpIdentity(
        profile: profile,
        knownPhoneE164: knownPhoneE164,
      );
      if (resolved == null) {
        _logDebug('missing_identity', keys: const ['user_id', 'phone']);
        return AuthMeFetchResult(
          ok: false,
          failureKind: AuthMeFailureKind.missingIdentity,
          error: const ApiError(
            code: 'PARSE_ERROR',
            message: 'Missing required profile identity fields',
          ),
          statusCode: statusCode,
        );
      }
      return AuthMeFetchResult(
        ok: true,
        profile: resolved,
        statusCode: statusCode,
      );
    } catch (error) {
      _logDebug('profile_parse_exception', keys: [error.runtimeType.toString()]);
      return AuthMeFetchResult(
        ok: false,
        failureKind: AuthMeFailureKind.parseError,
        error: const ApiError(
          code: 'PARSE_ERROR',
          message: 'Failed to parse profile data',
        ),
        statusCode: statusCode,
      );
    }
  }

  /// Fill missing phone from OTP-confirmed phone without treating optional gaps as parse failure.
  @visibleForTesting
  static MeProfileDto? resolvePostOtpIdentity({
    required MeProfileDto profile,
    String? knownPhoneE164,
  }) {
    final hasUserId = profile.userId > 0;
    if (!hasUserId) return null;

    final phone = profile.phone?.trim();
    if (phone != null && phone.isNotEmpty) {
      return profile;
    }

    final fallback = knownPhoneE164?.trim();
    if (fallback != null && fallback.isNotEmpty) {
      return profile.copyWith(phone: fallback);
    }
    return null;
  }

  static Map<String, dynamic>? _decodeJsonObject(String body) {
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map) {
        return Map<String, dynamic>.from(decoded);
      }
    } catch (_) {
      return null;
    }
    return null;
  }

  static Map<String, dynamic>? _coerceToMap(Object? value) {
    if (value is Map) return Map<String, dynamic>.from(value);
    if (value is String) {
      final trimmed = value.trim();
      if (trimmed.isEmpty) return null;
      try {
        final decoded = jsonDecode(trimmed);
        if (decoded is Map) return Map<String, dynamic>.from(decoded);
      } catch (_) {
        return null;
      }
    }
    return null;
  }

  static bool _isEnvelopeShape(Map<String, dynamic> json) {
    return json.containsKey('ok') ||
        json.containsKey('data') ||
        json.containsKey('error');
  }

  static bool _looksLikeProfileMap(Map<String, dynamic> json) {
    return json.containsKey('user_id') || json.containsKey('id');
  }

  static Map<String, dynamic> _profileOnlyMap(Map<String, dynamic> json) {
    final copy = Map<String, dynamic>.from(json);
    copy.remove('ok');
    copy.remove('data');
    copy.remove('error');
    return copy;
  }

  static void _logDebug(String reason, {required List<String> keys}) {
    if (!kDebugMode) return;
    debugPrint('[AuthMe] $reason keys=$keys');
  }
}
