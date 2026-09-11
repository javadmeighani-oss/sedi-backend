import '../../core/network/api_client.dart';
import '../../core/network/api_response.dart';

class LifestyleHealthHrDto {
  final String hrStatus;
  final double? latestValue;
  final String? latestReceivedAt;
  final String rangeKey;
  final List<Map<String, dynamic>> history;
  final String? availableFrom;
  final String? availableTo;

  const LifestyleHealthHrDto({
    required this.hrStatus,
    this.latestValue,
    this.latestReceivedAt,
    required this.rangeKey,
    this.history = const [],
    this.availableFrom,
    this.availableTo,
  });

  factory LifestyleHealthHrDto.fromJson(Map<String, dynamic> json) {
    final raw = json['history'];
    final hist = <Map<String, dynamic>>[];
    if (raw is List) {
      for (final e in raw) {
        if (e is Map) hist.add(Map<String, dynamic>.from(e));
      }
    }
    return LifestyleHealthHrDto(
      hrStatus: json['hr_status']?.toString() ?? 'INSUFFICIENT_DATA',
      latestValue: (json['latest_value'] is num)
          ? (json['latest_value'] as num).toDouble()
          : double.tryParse('${json['latest_value']}'),
      latestReceivedAt: json['latest_received_at']?.toString(),
      rangeKey: json['range_key']?.toString() ?? '7d',
      history: hist,
      availableFrom: json['available_from']?.toString(),
      availableTo: json['available_to']?.toString(),
    );
  }
}

class LifestyleHealthService {
  final ApiClient _api;
  LifestyleHealthService({ApiClient? apiClient})
      : _api = apiClient ?? ApiClient();

  Future<ApiResponse<LifestyleHealthHrDto>> fetchHr({String rangeKey = '7d'}) {
    return _api.get<LifestyleHealthHrDto>(
      '/lifestyle/health-hr',
      queryParams: {'range_key': rangeKey},
      parser: (data) {
        if (data is Map) {
          return LifestyleHealthHrDto.fromJson(Map<String, dynamic>.from(data));
        }
        return null;
      },
    );
  }
}
