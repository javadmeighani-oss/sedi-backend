import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../core/auth/auth_service.dart';
import '../../core/config/app_config.dart';

/// Deprecated legacy onboarding adapter only.
///
/// A3 chat transport is exclusively
/// `lib/services/chat/chat_service.dart` (+ SSE client).
/// Do not add chat send/stream/greeting here.
@Deprecated('Legacy onboarding path; A3 uses services/chat/chat_service.dart')
class ChatService {
  Future<Map<String, String>> _buildHeaders() async {
    final headers = <String, String>{
      'Content-Type': 'application/json',
    };
    final token = await AuthService.getToken();
    if (token != null && token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }
    return headers;
  }

  /// Setup onboarding — create user with username only (no password).
  Future<Map<String, dynamic>> setupOnboarding(
    String language, {
    required String name,
  }) async {
    if (AppConfig.useLocalMode) {
      return {
        'message': 'Welcome! This is local mode.',
        'user_id': null,
        'language': language,
      };
    }

    if (name.trim().isEmpty) {
      return {
        'message': 'Name is required and cannot be empty',
        'user_id': null,
        'language': null,
      };
    }

    try {
      final uri = Uri.parse('${AppConfig.baseUrl}/interact/onboarding');
      final headers = await _buildHeaders();
      final payload = {'name': name.trim()};

      final response = await http
          .post(
            uri,
            headers: {
              ...headers,
              'Content-Type': 'application/json',
            },
            body: jsonEncode(payload),
          )
          .timeout(const Duration(seconds: 30));

      if (response.statusCode == 200) {
        final body = jsonDecode(response.body);
        final userId = body['user_id'];
        int? userIdInt;
        if (userId is int) {
          userIdInt = userId;
        } else if (userId != null) {
          userIdInt = int.tryParse(userId.toString());
        }
        if (userIdInt == null) {
          return {
            'message': body['message']?.toString() ??
                'Server response missing user_id. Please try again.',
            'user_id': null,
            'language': body['language']?.toString() ?? language,
          };
        }
        return {
          'message': body['message']?.toString() ?? '',
          'user_id': userIdInt,
          'language': body['language']?.toString() ?? language,
        };
      }

      String errorMessage = 'Error creating account. Please try again.';
      try {
        final errorBody = jsonDecode(response.body);
        final detail = errorBody['detail']?.toString() ??
            errorBody['message']?.toString() ??
            '';
        if (detail.isNotEmpty) errorMessage = detail;
      } catch (_) {}
      return {
        'message': errorMessage,
        'user_id': null,
        'language': null,
      };
    } catch (e) {
      return {
        'message': 'Error creating account. Please try again.',
        'user_id': null,
        'language': null,
      };
    }
  }
}
