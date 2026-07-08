import 'me_profile.dart';

/// Shared parser for GET/PATCH `/auth/me` payloads.
MeProfileDto? parseMeProfileDto(Object? json) {
  if (json is! Map) return null;
  try {
    return MeProfileDto.fromJson(Map<String, dynamic>.from(json));
  } catch (_) {
    return null;
  }
}
