import '../../core/network/api_client.dart';
import '../../core/network/api_response.dart';

class LifestyleUserEventDto {
  final int id;
  final String title;
  final String? location;
  final String? eventType;
  final String status;
  final String? startsAt;
  final bool reminderEnabled;
  final List<int> reminderOffsets;

  const LifestyleUserEventDto({
    required this.id,
    required this.title,
    this.location,
    this.eventType,
    required this.status,
    this.startsAt,
    this.reminderEnabled = false,
    this.reminderOffsets = const [],
  });

  factory LifestyleUserEventDto.fromJson(Map<String, dynamic> json) {
    final offsets = <int>[];
    final raw = json['reminder_offsets'] ?? json['reminder_offsets_json'];
    if (raw is List) {
      for (final e in raw) {
        final n = int.tryParse('$e');
        if (n != null) offsets.add(n);
      }
    }
    return LifestyleUserEventDto(
      id: int.tryParse('${json['id']}') ?? 0,
      title: json['title']?.toString() ?? '',
      location: json['location']?.toString(),
      eventType: json['event_type']?.toString(),
      status: json['status']?.toString() ?? 'scheduled',
      startsAt: json['starts_at']?.toString(),
      reminderEnabled: json['reminder_enabled'] == true,
      reminderOffsets: offsets,
    );
  }
}

class LifestyleI8ActionDto {
  final String title;
  final String status;
  final String domain;
  const LifestyleI8ActionDto({
    required this.title,
    required this.status,
    required this.domain,
  });

  factory LifestyleI8ActionDto.fromJson(Map<String, dynamic> json) =>
      LifestyleI8ActionDto(
        title: json['title']?.toString() ?? '',
        status: json['status']?.toString() ?? 'upcoming',
        domain: json['domain']?.toString() ?? '',
      );
}

class LifestyleScheduleService {
  final ApiClient _api;
  LifestyleScheduleService({ApiClient? apiClient})
      : _api = apiClient ?? ApiClient();

  Future<ApiResponse<List<LifestyleUserEventDto>>> listEvents() {
    return _api.get<List<LifestyleUserEventDto>>(
      '/user/events',
      parser: (data) {
        if (data is! Map) return <LifestyleUserEventDto>[];
        final raw = data['events'];
        if (raw is! List) return <LifestyleUserEventDto>[];
        return raw
            .whereType<Map>()
            .map((e) => LifestyleUserEventDto.fromJson(Map<String, dynamic>.from(e)))
            .toList();
      },
    );
  }

  Future<ApiResponse<void>> patchReminder({
    required int eventId,
    required bool enabled,
    List<int>? offsets,
  }) {
    return _api.patch<void>(
      '/user/events/$eventId',
      body: {
        'reminder_enabled': enabled,
        if (offsets != null) 'reminder_offsets': offsets,
      },
      parser: (_) => null,
    );
  }

  Future<ApiResponse<List<LifestyleI8ActionDto>>> listI8Actions() {
    return _api.get<List<LifestyleI8ActionDto>>(
      '/lifestyle/schedule-actions',
      parser: (data) {
        if (data is! Map) return <LifestyleI8ActionDto>[];
        final raw = data['items'];
        if (raw is! List) return <LifestyleI8ActionDto>[];
        return raw
            .whereType<Map>()
            .map((e) => LifestyleI8ActionDto.fromJson(Map<String, dynamic>.from(e)))
            .toList();
      },
    );
  }
}
