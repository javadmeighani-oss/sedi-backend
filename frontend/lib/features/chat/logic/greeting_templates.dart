/// Approved Sedi intro greeting (FA/EN/AR). Short, professional Gate 3 copy.

String getIntroGreeting(String langCode) {
  final lang = langCode.toLowerCase();
  switch (lang) {
    case 'fa':
      return _greetingFa;
    case 'ar':
      return _greetingAr;
    case 'en':
    default:
      return _greetingEn;
  }
}

const String _greetingFa =
    'سلام، من صدی هستم؛ همراه هوشمند سلامت شما.\n'
    'برای گفت‌وگو، پیگیری حالتان و همراهی روزانه آماده‌ام.';

const String _greetingEn =
    "Hello, I'm Sedi — your intelligent health companion.\n"
    "I'm here to talk, follow how you feel, and support you each day.";

const String _greetingAr =
    'مرحبًا، أنا صدي — رفيقك الذكي في الصحة.\n'
    'أنا هنا للتحدث ومتابعة حالتك ومرافقتك يوميًا.';
