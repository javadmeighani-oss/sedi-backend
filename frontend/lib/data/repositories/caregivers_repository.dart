import '../../core/config/app_config.dart';
import '../../core/network/api_client.dart';
import '../../core/network/api_response.dart';
import '../dto/gate3/caregiver_dto.dart';

class CaregiversRepository {
  final ApiClient _client;

  CaregiversRepository({ApiClient? apiClient})
      : _client = apiClient ?? ApiClient(baseUrl: AppConfig.baseUrl);

  Future<ApiResponse<List<CaregiverDto>>> listCaregivers() {
    return _client.get<List<CaregiverDto>>(
      '/user/caregivers',
      parser: (v) {
        if (v is! Map) return <CaregiverDto>[];
        final list = v['caregivers'];
        if (list is! List) return <CaregiverDto>[];
        return list
            .map((e) => CaregiverDto.fromJson(
                e is Map<String, dynamic> ? e : <String, dynamic>{}))
            .where((c) => c.isActive && c.name.isNotEmpty)
            .toList();
      },
    );
  }

  Future<ApiResponse<CaregiverDto?>> createCaregiver(
      Map<String, dynamic> body) {
    return _client.post<CaregiverDto?>(
      '/user/caregivers',
      body: body,
      parser: (v) =>
          v is Map<String, dynamic> ? CaregiverDto.fromJson(v) : null,
    );
  }

  Future<ApiResponse<CaregiverDto?>> updateCaregiver(
    int id,
    Map<String, dynamic> body,
  ) {
    return _client.patch<CaregiverDto?>(
      '/user/caregivers/$id',
      body: body,
      parser: (v) =>
          v is Map<String, dynamic> ? CaregiverDto.fromJson(v) : null,
    );
  }

  Future<ApiResponse<CaregiverDto?>> deactivateCaregiver(int id) {
    return updateCaregiver(id, {'is_active': false});
  }
}
