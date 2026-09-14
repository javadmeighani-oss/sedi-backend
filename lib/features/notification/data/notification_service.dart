/// ============================================
/// NotificationService - Contract-Compliant API Client
/// ============================================
///
/// RESPONSIBILITY:
/// - Backend contract: GET /notifications, GET /notifications/unread,
///   POST /notifications/{id}/mark-read, POST /notifications/{id}/feedback
/// - Uses ApiClient; returns Map for backward compatibility
/// ============================================

import '../../../core/config/app_config.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/api_response.dart';
import '../../../data/models/notification_feedback.dart';

class NotificationService {
  final ApiClient _client;

  NotificationService({String? baseUrl, ApiClient? apiClient})
      : _client = apiClient ?? ApiClient(baseUrl: baseUrl ?? AppConfig.baseUrl);

  /// GET /notifications/ — list all for user
  Future<Map<String, dynamic>> getNotifications({
    required int userId,
    int limit = 20,
    int offset = 0,
  }) async {
    final resp = await _client.get<Map<String, dynamic>>(
      '/notifications/',
      queryParams: {
        'user_id': userId.toString(),
        'limit': limit.toString(),
        'offset': offset.toString(),
      },
      parser: (v) =>
          v == null ? null : Map<String, dynamic>.from(v as Map),
    );
    return _responseToMap(resp);
  }

  /// Parse unread count from fetchUnreadList response. Returns 0 if missing or not ok.
  /// Authority order: unread_count → total → count → notifications.length.
  /// Prefer unread_count so page-sized `count` never under-reports badge authority.
  static int parseUnreadCount(Map<String, dynamic> resp) {
    if (resp['ok'] != true) return 0;
    final data = resp['data'] as Map<String, dynamic>?;
    if (data == null) return 0;
    final unread = data['unread_count'];
    if (unread is int) return unread < 0 ? 0 : unread;
    final total = data['total'];
    if (total is int) return total < 0 ? 0 : total;
    final count = data['count'];
    if (count is int) return count < 0 ? 0 : count;
    final list = data['notifications'] as List<dynamic>?;
    return list?.length ?? 0;
  }

  /// GET /notifications/unread — list unread + count
  Future<Map<String, dynamic>> fetchUnreadList({
    required int userId,
    int limit = 20,
    String? type,
  }) async {
    final queryParams = <String, String>{
      'user_id': userId.toString(),
      'limit': limit.toString(),
    };
    if (type != null && type.isNotEmpty) queryParams['type'] = type;
    final resp = await _client.get<Map<String, dynamic>>(
      '/notifications/unread',
      queryParams: queryParams,
      parser: (v) =>
          v == null ? null : Map<String, dynamic>.from(v as Map),
    );
    return _responseToMap(resp);
  }

  /// POST /notifications/{notification_id}/mark-read
  Future<Map<String, dynamic>> markRead({
    required String notificationId,
    required int userId,
  }) async {
    final resp = await _client.post<Map<String, dynamic>>(
      '/notifications/$notificationId/mark-read',
      queryParams: {'user_id': userId.toString()},
      parser: (v) =>
          v == null ? null : Map<String, dynamic>.from(v as Map),
    );
    return _responseToMap(resp);
  }

  /// POST /notifications/{notification_id}/feedback — body: feedback, reason?, action?
  Future<Map<String, dynamic>> submitFeedback(
      NotificationFeedback feedback) async {
    final id = feedback.notificationId;
    final resp = await _client.post<Map<String, dynamic>>(
      '/notifications/$id/feedback',
      body: feedback.toBackendJson(),
      parser: (v) =>
          v == null ? null : Map<String, dynamic>.from(v as Map),
    );
    return _responseToMap(resp);
  }

  static Map<String, dynamic> _responseToMap<T>(ApiResponse<T> r) {
    return {
      'ok': r.ok,
      'data': r.data,
      if (r.error != null) 'error': r.error!.toJson(),
    };
  }
}
