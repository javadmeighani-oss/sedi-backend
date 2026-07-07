class AppConfig {
  /// Official public backend API (HTTPS). Do not use direct IP:8000 — port is not publicly reachable.
  static const String baseUrl = "https://api.sedi-ai.com";

  /// اجرای لوکال با پاسخ‌های Mock => true
  /// اتصال به بک‌اند واقعی => false
  static const bool useLocalMode = false;
}
