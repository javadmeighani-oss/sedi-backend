import '../../../data/dto/auth/me_profile.dart';

/// Decides whether A2 selected language must PATCH `/auth/me`.
class A2LanguageSync {
  A2LanguageSync._();

  /// Returns true when backend preferred_language differs from A2 selection.
  static bool needsPatch({
    required MeProfileDto backendMe,
    required String? selectedLanguage,
  }) {
    if (selectedLanguage == null || selectedLanguage.trim().isEmpty) {
      return false;
    }
    final selected = selectedLanguage.trim().toLowerCase();
    final backend = (backendMe.preferredLanguage ?? '').trim().toLowerCase();
    return backend != selected;
  }

  static MeUpdateDto patchDto(String selectedLanguage) {
    return MeUpdateDto(preferredLanguage: selectedLanguage.trim());
  }
}
