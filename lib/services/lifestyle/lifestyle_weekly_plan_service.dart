import '../../core/network/api_client.dart';
import '../../core/network/api_response.dart';
import '../../data/dto/lifestyle/lifestyle_weekly_plan_dto.dart';

/// Shared read-only transport for `GET /lifestyle/weekly-plan`.
/// Used by Nutrition and Exercise presentation (one service only).
class LifestyleWeeklyPlanService {
  final ApiClient _api;

  LifestyleWeeklyPlanService({ApiClient? apiClient})
      : _api = apiClient ?? ApiClient();

  Future<ApiResponse<LifestyleWeeklyPlanDto>> fetchWeeklyPlan() {
    return _api.get<LifestyleWeeklyPlanDto>(
      '/lifestyle/weekly-plan',
      parser: (data) {
        if (data is Map) {
          return LifestyleWeeklyPlanDto.fromJson(
            Map<String, dynamic>.from(data),
          );
        }
        return null;
      },
    );
  }
}
