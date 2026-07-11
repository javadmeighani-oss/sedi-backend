import '../../core/config/app_config.dart';
import '../../core/network/api_client.dart';
import '../../core/network/api_response.dart';

class Gate3CareRepository {
  final ApiClient _client;

  Gate3CareRepository({ApiClient? apiClient})
      : _client = apiClient ?? ApiClient(baseUrl: AppConfig.baseUrl);

  Future<ApiResponse<Map<String, dynamic>?>> fetchContext() {
    return _client.get<Map<String, dynamic>?>(
      '/care/context',
      parser: (v) => v is Map ? Map<String, dynamic>.from(v) : null,
    );
  }

  Future<ApiResponse<List<Map<String, dynamic>>>> fetchRecommendations() {
    return _client.get<List<Map<String, dynamic>>>(
      '/care/recommendations',
      parser: (v) => _listFromEnvelope(v, 'recommendations'),
    );
  }

  Future<ApiResponse<List<Map<String, dynamic>>>> fetchFollowUps() {
    return _client.get<List<Map<String, dynamic>>>(
      '/care/follow-ups',
      parser: (v) => _listFromEnvelope(v, 'follow_ups'),
    );
  }

  List<Map<String, dynamic>> _listFromEnvelope(Object? v, String key) {
    if (v is! Map) return [];
    final list = v[key] ?? v['items'];
    if (list is! List) return [];
    return list
        .map((e) => e is Map<String, dynamic> ? e : <String, dynamic>{})
        .toList();
  }
}
