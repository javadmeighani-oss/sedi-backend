import '../../../data/dto/auth/me_profile.dart';

/// Outcome of reconciling A2 selected language with GET `/auth/me`.
enum A2LanguageSyncOutcome {
  /// Backend already matches selection — no PATCH.
  matched,

  /// PATCH succeeded; [A2LanguageSyncResult.profile] is backend-confirmed.
  patched,

  /// PATCH required but failed — must NOT enter A3 with stale language.
  patchFailed,
}

class A2LanguageSyncResult {
  final A2LanguageSyncOutcome outcome;
  final MeProfileDto? profile;

  const A2LanguageSyncResult({
    required this.outcome,
    this.profile,
  });

  bool get mayEnterA3 =>
      outcome == A2LanguageSyncOutcome.matched ||
      outcome == A2LanguageSyncOutcome.patched;

  MeProfileDto? get confirmedProfile => mayEnterA3 ? profile : null;
}

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

  /// Pure classifier after a PATCH attempt (testable without I/O).
  static A2LanguageSyncResult classifyAfterPatchAttempt({
    required MeProfileDto backendMeBeforePatch,
    required String? selectedLanguage,
    required bool patchOk,
    required MeProfileDto? patchedProfile,
  }) {
    if (!needsPatch(
      backendMe: backendMeBeforePatch,
      selectedLanguage: selectedLanguage,
    )) {
      return A2LanguageSyncResult(
        outcome: A2LanguageSyncOutcome.matched,
        profile: backendMeBeforePatch,
      );
    }
    if (patchOk && patchedProfile != null) {
      return A2LanguageSyncResult(
        outcome: A2LanguageSyncOutcome.patched,
        profile: patchedProfile,
      );
    }
    return const A2LanguageSyncResult(
      outcome: A2LanguageSyncOutcome.patchFailed,
      profile: null,
    );
  }
}
