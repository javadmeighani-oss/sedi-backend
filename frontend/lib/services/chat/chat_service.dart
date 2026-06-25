import 'package:flutter/foundation.dart';

import '../../core/auth/user_identity_service.dart';
import '../../core/auth/auth_service.dart';
import '../../core/network/api_client.dart';
import '../../core/network/api_error.dart';
import '../../core/network/api_response.dart';
import '../../data/dto/chat/chat_send_request.dart';
import '../../data/dto/chat/chat_send_response.dart';

class ChatService {
  final ApiClient _apiClient;

  ChatService({ApiClient? apiClient}) : _apiClient = apiClient ?? ApiClient();

  Future<ApiResponse<ChatSendResponse>> sendMessage({
    required String message,
    String? language,
    int? userId,
  }) async {
    final text = message.trim();
    if (text.isEmpty) {
      return const ApiResponse<ChatSendResponse>(
        ok: false,
        error: ApiError(
            code: 'VALIDATION_ERROR', message: 'Message cannot be empty'),
      );
    }

    final resolvedUserId = await _resolveUserId(userId);
    if (resolvedUserId == null) {
      return const ApiResponse<ChatSendResponse>(
        ok: false,
        error: ApiError(
          code: 'USER_ID_REQUIRED',
          message: 'User identity is required before sending chat messages.',
        ),
      );
    }

    final request = ChatSendRequest(
      userId: resolvedUserId,
      message: text,
    );

    final headers = <String, String>{};
    if (language != null && language.trim().isNotEmpty) {
      headers['Accept-Language'] = language.trim();
    }

    if (kDebugMode) {
      debugPrint('[ChatService] POST /interact/chat');
      debugPrint(
          '[ChatService] payload: user_id=$resolvedUserId message_len=${text.length}');
    }

    final response = await _apiClient.post<ChatSendResponse>(
      '/interact/chat',
      body: request.toJson(),
      extraHeaders: headers.isEmpty ? null : headers,
      parser: (json) {
        if (json is Map) {
          return ChatSendResponse.fromJson(Map<String, dynamic>.from(json));
        }
        return null;
      },
    );

    if (kDebugMode) {
      debugPrint(
        '[ChatService] envelope: ok=${response.ok} status=${response.statusCode} error=${response.error?.code}',
      );
    }
    return response;
  }

  /// Fetches personalized greeting via GET /interact/greeting (JWT + refresh via ApiClient).
  Future<ApiResponse<String>> fetchGreeting({
    required int userId,
    String? language,
    String? name,
  }) async {
    final resolvedUserId = await _resolveUserId(userId);
    if (resolvedUserId == null) {
      return const ApiResponse<String>(
        ok: false,
        error: ApiError(
          code: 'USER_ID_REQUIRED',
          message: 'User identity is required before fetching greeting.',
        ),
      );
    }

    final lang = (language != null && language.trim().isNotEmpty)
        ? language.trim()
        : 'en';
    final queryParams = <String, String>{
      'user_id': resolvedUserId.toString(),
      'lang': lang,
    };
    if (name != null && name.trim().isNotEmpty) {
      queryParams['name'] = name.trim();
    }

    final headers = <String, String>{'Accept-Language': lang};

    if (kDebugMode) {
      debugPrint('[ChatService] GET /interact/greeting user_id=$resolvedUserId');
    }

    return _apiClient.get<String>(
      '/interact/greeting',
      queryParams: queryParams,
      extraHeaders: headers,
      parser: (json) {
        if (json is Map) {
          final message = json['message']?.toString();
          if (message != null && message.trim().isNotEmpty) {
            return message.trim();
          }
        }
        return null;
      },
    );
  }

  Future<int?> _resolveUserId(int? explicitUserId) async {
    if (explicitUserId != null && explicitUserId > 0) return explicitUserId;
    final resolved = await UserIdentityService.resolveUserId();
    if (resolved != null) return resolved;
    final token = await AuthService.getToken();
    if (token == null || token.isEmpty) return null;
    return UserIdentityService.resolveUserId(forceRefresh: true);
  }
}
