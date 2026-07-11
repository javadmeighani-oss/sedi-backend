import '../../core/config/app_config.dart';
import '../../core/network/api_client.dart';
import '../../core/network/api_response.dart';
import '../dto/lifestyle_summary_response.dart';

class Gate3UserDataRepository {
  final ApiClient _client;

  Gate3UserDataRepository({ApiClient? apiClient})
      : _client = apiClient ?? ApiClient(baseUrl: AppConfig.baseUrl);

  Future<ApiResponse<Map<String, dynamic>?>> updateMedication(
    int id,
    Map<String, dynamic> body,
  ) {
    return _client.patch<Map<String, dynamic>?>(
      '/user/medications/$id',
      body: body,
      parser: (v) => v is Map ? Map<String, dynamic>.from(v) : null,
    );
  }

  Future<ApiResponse<List<Map<String, dynamic>>>> fetchMedications() {
    return _getList('/user/medications', 'medications');
  }

  Future<ApiResponse<List<Map<String, dynamic>>>> fetchDoctors() {
    return _getList('/user/doctors', 'doctors');
  }

  Future<ApiResponse<List<Map<String, dynamic>>>> fetchEvents() {
    return _getList('/user/events', 'events');
  }

  Future<ApiResponse<List<Map<String, dynamic>>>> fetchHabits() {
    return _getList('/user/habits', 'habits');
  }

  Future<ApiResponse<List<Map<String, dynamic>>>> fetchGoals() {
    return _getList('/user/goals', 'goals');
  }

  Future<ApiResponse<List<Map<String, dynamic>>>> fetchRestrictions() {
    return _getList('/user/restrictions', 'restrictions');
  }

  Future<ApiResponse<List<Map<String, dynamic>>>> fetchCarePlanItems() {
    return _getList('/user/care-plan-items', 'care_plan_items');
  }

  Future<ApiResponse<List<Map<String, dynamic>>>> fetchLifestyleEvents() {
    return _getList('/user/lifestyle-events', 'lifestyle_events');
  }

  Future<ApiResponse<LifestyleSummaryResponse?>> fetchLifestyleSummary({
    String? lang,
  }) {
    return _client.get<LifestyleSummaryResponse?>(
      '/lifestyle/summary',
      queryParams: lang != null && lang.isNotEmpty ? {'lang': lang} : null,
      parser: (v) => LifestyleSummaryResponse.fromApiData(v),
    );
  }

  Future<ApiResponse<Map<String, dynamic>?>> fetchLifestyleContext() {
    return _client.get<Map<String, dynamic>?>(
      '/lifestyle/context',
      parser: (v) => v is Map ? Map<String, dynamic>.from(v) : null,
    );
  }

  Future<ApiResponse<List<Map<String, dynamic>>>> _getList(
    String path,
    String key,
  ) {
    return _client.get<List<Map<String, dynamic>>>(
      path,
      parser: (v) {
        if (v is! Map) return [];
        final list = v[key] ?? v['items'];
        if (list is! List) return [];
        return list
            .map((e) => e is Map<String, dynamic> ? e : <String, dynamic>{})
            .toList();
      },
    );
  }
}
