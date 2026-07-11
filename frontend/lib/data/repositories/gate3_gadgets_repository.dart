import '../../core/config/app_config.dart';
import '../../core/network/api_client.dart';
import '../../core/network/api_response.dart';

class Gate3GadgetsRepository {
  final ApiClient _client;

  Gate3GadgetsRepository({ApiClient? apiClient})
      : _client = apiClient ?? ApiClient(baseUrl: AppConfig.baseUrl);

  Future<ApiResponse<Map<String, dynamic>?>> fetchHubStatus() {
    return _client.get<Map<String, dynamic>?>(
      '/devices/hub-status',
      parser: (v) => v is Map ? Map<String, dynamic>.from(v) : null,
    );
  }
}
