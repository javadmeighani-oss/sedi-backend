import '../../core/network/api_client.dart';
import '../../core/network/api_error.dart';
import '../../core/network/api_response.dart';
import '../../core/auth/user_identity_service.dart';
import '../../data/dto/notifications/gate4_notification_metadata.dart';
import '../../data/dto/notifications/notification_feedback_dto.dart';
import '../../data/dto/notifications/notification_list_response_dto.dart';
import '../../data/models/notification_item.dart';

/// In-memory bounded dedupe for notification_id + action_id feedback.
class NotificationFeedbackDedupe {
  NotificationFeedbackDedupe({this.maxSize = 100});

  final int maxSize;
  final List<String> _order = <String>[];
  final Set<String> _keys = <String>{};

  static String keyFor(int notificationId, String actionId) =>
      '$notificationId::$actionId';

  bool alreadySent(int notificationId, String actionId) =>
      _keys.contains(keyFor(notificationId, actionId));

  void mark(int notificationId, String actionId) {
    final key = keyFor(notificationId, actionId);
    if (_keys.contains(key)) return;
    _keys.add(key);
    _order.add(key);
    while (_order.length > maxSize) {
      final oldest = _order.removeAt(0);
      _keys.remove(oldest);
    }
  }
}

class NotificationsService {
  final ApiClient _apiClient;
  final NotificationFeedbackDedupe _feedbackDedupe;

  NotificationsService({
    ApiClient? apiClient,
    NotificationFeedbackDedupe? feedbackDedupe,
  })  : _apiClient = apiClient ?? ApiClient(),
        _feedbackDedupe = feedbackDedupe ?? NotificationFeedbackDedupe();

  Future<ApiResponse<List<NotificationItem>>> listInbox({
    bool unreadOnly = false,
    int limit = 50,
    String? cursor,
  }) async {
    final userId = await UserIdentityService.resolveUserId();
    if (userId == null) {
      return const ApiResponse<List<NotificationItem>>(
        ok: false,
        data: [],
        error: ApiError(
          code: 'USER_ID_REQUIRED',
          message: 'User identity is required to load notifications.',
        ),
      );
    }

    final queryParams = <String, String>{
      'user_id': userId.toString(),
      'limit': limit.toString(),
      if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
    };

    final path = unreadOnly ? '/notifications/unread' : '/notifications/';
    final response = await _apiClient.get<NotificationListResponseDto>(
      path,
      queryParams: queryParams,
      parser: (json) {
        if (json is Map) {
          return NotificationListResponseDto.fromJson(
              Map<String, dynamic>.from(json));
        }
        return null;
      },
    );

    final payload = response.data;
    final dtos = payload?.notifications ?? const [];
    final items = dtos
        .map((dto) => NotificationItem.fromDto(dto))
        .toList(growable: false);

    final deduped = <int, NotificationItem>{};
    for (final item in items) {
      deduped[item.id] = item;
    }
    final sorted = deduped.values.toList()
      ..sort((a, b) => b.createdAt.compareTo(a.createdAt));

    return ApiResponse<List<NotificationItem>>(
      ok: response.ok,
      data: sorted,
      error: response.error,
      statusCode: response.statusCode,
    );
  }

  Future<ApiResponse<void>> markRead(int id) async {
    final userId = await UserIdentityService.resolveUserId();
    if (userId == null) {
      return const ApiResponse<void>(
        ok: false,
        error: ApiError(
          code: 'USER_ID_REQUIRED',
          message: 'User identity is required to mark notifications as read.',
        ),
      );
    }

    final response = await _apiClient.post<Object?>(
      '/notifications/$id/mark-read',
      queryParams: {'user_id': userId.toString()},
      parser: (_) => null,
    );
    return ApiResponse<void>(
      ok: response.ok,
      error: response.error,
      statusCode: response.statusCode,
    );
  }

  /// Legacy like/dislike feedback (non-inbox callers).
  Future<ApiResponse<void>> sendFeedback(
    int id, {
    required bool liked,
  }) async {
    final userId = await UserIdentityService.resolveUserId();
    if (userId == null) {
      return const ApiResponse<void>(
        ok: false,
        error: ApiError(
          code: 'USER_ID_REQUIRED',
          message: 'User identity is required to send notification feedback.',
        ),
      );
    }

    final dto = NotificationFeedbackDto.legacyLiked(
      liked: liked,
      timestamp: DateTime.now(),
    );
    final response = await _apiClient.post<Object?>(
      '/notifications/$id/feedback',
      queryParams: {'user_id': userId.toString()},
      body: dto.toJson(),
      parser: (_) => null,
    );
    return ApiResponse<void>(
      ok: response.ok,
      error: response.error,
      statusCode: response.statusCode,
    );
  }

  /// Canonical Gate 4 V1 feedback. Dedupes by notification ID + action ID.
  Future<ApiResponse<void>> sendCanonicalFeedback(
    int id, {
    required String actionId,
    bool force = false,
  }) async {
    if (!kGate4V1ActionIds.contains(actionId)) {
      return const ApiResponse<void>(
        ok: false,
        error: ApiError(
          code: 'INVALID_ACTION',
          message: 'Action is not allowlisted.',
        ),
      );
    }
    if (!force && _feedbackDedupe.alreadySent(id, actionId)) {
      return const ApiResponse<void>(ok: true);
    }

    final userId = await UserIdentityService.resolveUserId();
    if (userId == null) {
      return const ApiResponse<void>(
        ok: false,
        error: ApiError(
          code: 'USER_ID_REQUIRED',
          message: 'User identity is required to send notification feedback.',
        ),
      );
    }

    final dto = NotificationFeedbackDto.canonical(
      actionId: actionId,
      timestamp: DateTime.now(),
    );
    final response = await _apiClient.post<Object?>(
      '/notifications/$id/feedback',
      queryParams: {'user_id': userId.toString()},
      body: dto.toJson(),
      parser: (_) => null,
    );
    if (response.ok) {
      _feedbackDedupe.mark(id, actionId);
    }
    return ApiResponse<void>(
      ok: response.ok,
      error: response.error,
      statusCode: response.statusCode,
    );
  }
}
