import '../../core/network/api_client.dart';
import '../../core/network/api_response.dart';

class LifestyleHealthHrDto {
  /// Authoritative gadget status only when [hrStatusSource] is DEVICE_REPORTED.
  final String? hrStatus;
  final String? hrStatusSource;
  final String? hrStatusObservedAt;
  /// Legacy MAD compact — never treat as DEVICE_REPORTED authority.
  final String? hrStabilityCompact;
  final double? latestValue;
  final String? latestReceivedAt;
  final String rangeKey;
  final List<Map<String, dynamic>> history;
  final String? availableFrom;
  final String? availableTo;

  const LifestyleHealthHrDto({
    this.hrStatus,
    this.hrStatusSource,
    this.hrStatusObservedAt,
    this.hrStabilityCompact,
    this.latestValue,
    this.latestReceivedAt,
    required this.rangeKey,
    this.history = const [],
    this.availableFrom,
    this.availableTo,
  });

  static const _deviceStatuses = {'STABLE', 'UNSTABLE'};

  /// True only for authoritative DEVICE_REPORTED STABLE|UNSTABLE.
  bool get isDeviceReportedStatus {
    final source = (hrStatusSource ?? '').trim().toUpperCase();
    final status = (hrStatus ?? '').trim().toUpperCase();
    return source == 'DEVICE_REPORTED' && _deviceStatuses.contains(status);
  }

  factory LifestyleHealthHrDto.fromJson(Map<String, dynamic> json) {
    final raw = json['history'];
    final hist = <Map<String, dynamic>>[];
    if (raw is List) {
      for (final e in raw) {
        if (e is Map) hist.add(Map<String, dynamic>.from(e));
      }
    }
    final statusRaw = json['hr_status']?.toString().trim();
    final status =
        (statusRaw == null || statusRaw.isEmpty) ? null : statusRaw;
    return LifestyleHealthHrDto(
      hrStatus: status,
      hrStatusSource: json['hr_status_source']?.toString() ??
          json['status_source']?.toString() ??
          json['status_provenance']?.toString(),
      hrStatusObservedAt: json['hr_status_observed_at']?.toString(),
      hrStabilityCompact: json['hr_stability_compact']?.toString(),
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
