import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../../core/auth/auth_service.dart';
import '../../core/config/app_config.dart';
import '../../core/network/api_client.dart';
import '../dto/history_response.dart';
import '../dto/interact_request.dart';

/// Result of a chat POST: status code and raw body (for ChatService to parse).
/// Backend /interact/chat returns raw JSON (not ApiResponse envelope).
class ChatRepositoryResult {
  final int statusCode;
  final String body;

  const ChatRepositoryResult({required this.statusCode, required this.body});
}

/// Sends chat request to POST /interact/chat with JSON body from [request].
/// Does not log secrets. Caller handles 422/502 and parses body.
Future<ChatRepositoryResult> sendChat(InteractRequest request) async {
  final baseUri = Uri.parse(AppConfig.baseUrl);
  final uri = Uri(
    scheme: baseUri.scheme,
    host: baseUri.host,
    port: baseUri.port,
    path: '/interact/chat',
  );
  final headers = <String, String>{
    'Content-Type': 'application/json',
  };
  final token = await AuthService.getToken();
  if (token != null && token.isNotEmpty) {
    headers['Authorization'] = 'Bearer $token';
  }
  final body = jsonEncode(request.toJson());
  final response = await http
      .post(uri, headers: headers, body: body)
      .timeout(const Duration(seconds: 15), onTimeout: () {
    throw Exception('Connection timeout');
  });
  return ChatRepositoryResult(statusCode: response.statusCode, body: response.body);
}

/// Fetches chat history from GET /memory/history via authenticated [ApiClient].
///
/// JWT is the only identity source — never sends `user_id`.
/// Response is a raw top-level HistoryResponse (not an ApiResponse envelope).
Future<HistoryResponse> fetchHistory({
  required String group,
  int limit = 50,
  int offset = 0,
  ApiClient? apiClient,
}) async {
  final client = apiClient ?? ApiClient();
  final response = await client.getHttpResponse(
    '/memory/history',
    queryParams: {
      'group': group,
      'limit': limit.toString(),
      'offset': offset.toString(),
    },
  );

  if (response.statusCode != 200) {
    if (kDebugMode) {
      debugPrint('[ChatRepository] history failed status=${response.statusCode}');
    }
    throw Exception('History failed: ${response.statusCode}');
  }

  Map<String, dynamic> json;
  try {
    final decoded = jsonDecode(response.body);
    if (decoded is! Map) {
      throw Exception('History parse error');
    }
    json = Map<String, dynamic>.from(decoded);
  } catch (_) {
    throw Exception('History parse error');
  }

  // Guard against accidentally treating envelope as history.
  if (json.containsKey('ok') &&
      json.containsKey('data') &&
      json['data'] is Map) {
    json = Map<String, dynamic>.from(json['data'] as Map);
  }

  return HistoryResponse.fromJson(json);
}
