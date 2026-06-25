class AppConfig {
  /// API base URL is controlled by compile-time define.
  /// Default is production endpoint if no define is provided.
  static const String baseUrl = String.fromEnvironment(
    'SEDI_API_BASE_URL',
    defaultValue: 'https://api.sedi-ai.com',
  );

  /// Local mode can still be enabled through compile-time define if needed.
  static const bool useLocalMode = bool.fromEnvironment('SEDI_USE_LOCAL_MODE', defaultValue: false);
}
