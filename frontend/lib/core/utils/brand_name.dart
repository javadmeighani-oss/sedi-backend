/// Centralized brand name: EN = "Sedi", FA/AR = "صدی".
/// Use for all UI strings, notifications, onboarding, and intro.

String sediBrandName(String langCode) {
  final lang = langCode.toLowerCase();
  if (lang == 'fa' || lang == 'ar') return 'صدی';
  return 'Sedi';
}
