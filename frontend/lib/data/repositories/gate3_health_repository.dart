import '../../core/config/app_config.dart';
import '../../core/network/api_client.dart';
import '../../core/network/api_response.dart';

class Gate3HealthRepository {
  final ApiClient _client;

  Gate3HealthRepository({ApiClient? apiClient})
      : _client = apiClient ?? ApiClient(baseUrl: AppConfig.baseUrl);

  Future<ApiResponse<Map<String, dynamic>?>> fetchVitalsSummary() {
    return _client.get<Map<String, dynamic>?>(
      '/health/vitals-summary',
      parser: (v) => v is Map ? Map<String, dynamic>.from(v) : null,
    );
  }
}
