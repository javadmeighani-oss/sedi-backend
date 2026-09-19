import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'me_profile.dart';

/// Debug-only reasons for `/auth/me` profile parse failures.
enum MeProfileParseFailureReason {
  notObject,
  missingIdentity,
  invalidJson,
  unexpectedError,
}

/// Extract a profile map from backend `/auth/me` payload shapes.
Map<String, dynamic>? extractMeProfileMap(Object? json) {
  final map = _coerceToMap(json);
  if (map == null) return null;
  return _unwrapProfileMap(map);
}

/// True when [profile] has the minimum identity fields required after OTP.
bool isMeProfileIdentityValid(MeProfileDto profile) {
  final hasUserId = profile.userId > 0;
  final hasPhone = profile.phone != null && profile.phone!.trim().isNotEmpty;
  return hasUserId && hasPhone;
}

/// Shared parser for GET/PATCH `/auth/me` payloads.
MeProfileDto? parseMeProfileDto(Object? json) {
  final map = extractMeProfileMap(json);
  if (map == null) {
    _logParseFailure(MeProfileParseFailureReason.notObject);
    return null;
  }

  try {
    final profile = MeProfileDto.fromJson(map);
    if (!isMeProfileIdentityValid(profile)) {
      _logParseFailure(MeProfileParseFailureReason.missingIdentity);
      return null;
    }
    return profile;
  } catch (error, stackTrace) {
    _logParseFailure(
      MeProfileParseFailureReason.unexpectedError,
      error: error,
      stackTrace: stackTrace,
    );
    return null;
  }
}

Map<String, dynamic>? _coerceToMap(Object? json) {
  if (json == null) return null;
  if (json is Map) {
    return Map<String, dynamic>.from(json);
  }
  if (json is String) {
    final trimmed = json.trim();
    if (trimmed.isEmpty) return null;
    try {
      final decoded = jsonDecode(trimmed);
      if (decoded is Map) {
        return Map<String, dynamic>.from(decoded);
      }
      _logParseFailure(MeProfileParseFailureReason.invalidJson);
      return null;
    } catch (_) {
      _logParseFailure(MeProfileParseFailureReason.invalidJson);
      return null;
    }
  }
  if (json is List) {
    for (final item in json) {
      final map = _coerceToMap(item);
      if (map != null) return map;
    }
  }
  return null;
}

Map<String, dynamic>? _unwrapProfileMap(Map<String, dynamic> map) {
  if (_hasIdentityFields(map)) {
    return map;
  }

  for (final key in const ['user', 'profile', 'me']) {
    final nestedMap = _coerceToMap(map[key]);
    if (nestedMap != null) {
      final unwrapped = _unwrapProfileMap(nestedMap);
      if (unwrapped != null && _hasIdentityFields(unwrapped)) {
        return unwrapped;
      }
    }
  }

  final nestedData = _coerceToMap(map['data']);
  if (nestedData != null) {
    final unwrapped = _unwrapProfileMap(nestedData);
    if (unwrapped != null) {
      return unwrapped;
    }
  }

  return map;
}

bool _hasIdentityFields(Map<String, dynamic> map) {
  return map.containsKey('user_id') || map.containsKey('id');
}

void _logParseFailure(
  MeProfileParseFailureReason reason, {
  Object? error,
  StackTrace? stackTrace,
}) {
  if (!kDebugMode) return;
  debugPrint('[MeProfile] parse failed: $reason');
  if (error != null) {
    debugPrint('[MeProfile] error: $error');
  }
  if (stackTrace != null) {
    debugPrint('[MeProfile] stack: $stackTrace');
  }
}
