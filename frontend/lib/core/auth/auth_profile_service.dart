import '../../data/dto/auth/me_profile.dart';
import '../../data/dto/auth/me_profile_parser.dart';
import '../../data/models/user_profile.dart';
import '../network/api_client.dart';
import '../network/api_response.dart';
import '../utils/user_profile_manager.dart';

/// Backend profile source of truth: GET/PATCH /auth/me.
class AuthProfileService {
  final ApiClient _apiClient;

  AuthProfileService({ApiClient? apiClient})
      : _apiClient = apiClient ?? ApiClient(timeout: const Duration(seconds: 30));

  Future<ApiResponse<MeProfileDto>> fetchMe({
    String? accessToken,
    bool recoverSessionOn401 = true,
  }) async {
    return _apiClient.get<MeProfileDto>(
      '/auth/me',
      accessToken: accessToken,
      recoverSessionOn401: recoverSessionOn401,
      parser: parseMeProfileDto,
    );
  }

  Future<ApiResponse<MeProfileDto>> patchMe(
    MeUpdateDto update, {
    String? accessToken,
    bool recoverSessionOn401 = true,
  }) async {
    return _apiClient.patch<MeProfileDto>(
      '/auth/me',
      body: update.toJson(),
      accessToken: accessToken,
      recoverSessionOn401: recoverSessionOn401,
      parser: parseMeProfileDto,
    );
  }

  /// GET /auth/me and persist confirmed backend profile locally.
  Future<ApiResponse<MeProfileDto>> fetchAndCacheProfile() async {
    final me = await fetchMe();
    if (!me.ok || me.data == null) return me;
    await cacheProfileFromBackend(me.data!);
    return me;
  }

  Future<void> cacheProfileFromBackend(MeProfileDto me) async {
    final existing = await UserProfileManager.loadProfile();
    final profile = existing.copyWith(
      userId: me.userId,
      phoneNumber: me.phone,
      name: me.name,
      preferredLanguage: me.preferredLanguage ?? existing.preferredLanguage,
      gender: _mapSexToGender(me.sex) ?? existing.gender,
      calendarType: me.calendarType ?? existing.calendarType,
      birthDay: me.birthDay ?? existing.birthDay,
      birthMonth: me.birthMonth ?? existing.birthMonth,
      birthYear: me.birthYear ?? existing.birthYear,
      dateOfBirth: me.dateOfBirth ?? existing.dateOfBirth,
      isVerified: true,
    );
    await UserProfileManager.saveProfile(profile);
  }

  static String? _mapSexToGender(String? sex) {
    if (sex == null || sex.isEmpty) return null;
    final s = sex.toLowerCase();
    if (s == 'male' || s == 'female' || s == 'other') return s;
    return null;
  }

  static UserProfile toUserProfile(MeProfileDto me) {
    return UserProfile(
      userId: me.userId,
      phoneNumber: me.phone,
      name: me.name,
      preferredLanguage: me.preferredLanguage ?? 'en',
      gender: _mapSexToGender(me.sex),
      calendarType: me.calendarType,
      birthDay: me.birthDay,
      birthMonth: me.birthMonth,
      birthYear: me.birthYear,
      dateOfBirth: me.dateOfBirth,
      isVerified: true,
    );
  }
}
