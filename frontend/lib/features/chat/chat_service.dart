import 'dart:convert';
import 'dart:math';
import 'package:http/http.dart' as http;

import '../../../core/auth/auth_service.dart';
import '../../../core/config/app_config.dart';
import '../../../core/debug/chat_last_error_dump.dart';
import '../../../core/utils/user_preferences.dart';
import '../../../data/dto/interact_request.dart';
import '../../../data/repositories/chat_repository.dart';

/// LEGACY ChatService — used by [ChatController] for greeting/onboarding paths.
/// New chat sends go through `services/chat/chat_service.dart` (V1 `/interact/chat`).
/// Not part of gate routing; do not use for new features.
void _chatDebugLog(String message) {
  // Legacy chat service — keep silent to avoid logging tokens, OTP, or PII.
}

/// ------------------------------------------------------------
/// ChatService
///
/// RESPONSIBILITY:
/// - Send user message to backend (or mock)
/// - Return raw assistant reply
/// - NO UI logic
/// - NO personality / intent logic
/// ------------------------------------------------------------
class ChatService {
  /// Build request headers with optional Authorization
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

  /// Minimal mock response for frontend development
  /// Personality & intelligence handled elsewhere
  String _mockReply(String userMessage) {
    final replies = <String>[
      'I understand.',
      'Got it.',
      'Please continue.',
      'Thanks for sharing.',
      'I am processing your message.',
    ];

    return replies[Random().nextInt(replies.length)];
  }

  /// Get greeting from backend (for new or returning users)
  /// Returns greeting message or null if backend unavailable
  /// CRITICAL: userId is required to prevent anonymous user creation
  Future<String?> getGreeting({
    String? userName,
    String? userPassword,
    String? language,
    int? userId, // CRITICAL: user_id to prevent anonymous user creation
  }) async {
    // ---------------- LOCAL MODE ----------------
    if (AppConfig.useLocalMode) {
      return null; // No greeting in local mode, use fallback
    }

    // ---------------- BACKEND MODE ----------------
    try {
      final currentLang = language ?? await UserPreferences.getUserLanguage();
      final lang = currentLang.isNotEmpty ? currentLang : 'en';

      // For new users without credentials, we can't use /greeting endpoint
      // Instead, we'll use /chat with a special greeting message
      // This allows backend to generate appropriate greeting
      final queryParams = <String, String>{
        'message': '__GREETING__', // Special marker for greeting
        'lang': lang,
      };

      // CRITICAL: Add user_id if available (prevents anonymous user creation)
      if (userId != null) {
        queryParams['user_id'] = userId.toString();
  _chatDebugLog('[ChatService] Adding user_id to greeting request: $userId');
      }

      // Add credentials if available
      if (userName != null && userName.isNotEmpty) {
        queryParams['name'] = userName.trim();
      }
      if (userPassword != null && userPassword.isNotEmpty) {
        queryParams['secret_key'] = userPassword.trim();
      }

      final baseUri = Uri.parse(AppConfig.baseUrl);
      final uri = Uri(
        scheme: baseUri.scheme,
        host: baseUri.host,
        port: baseUri.port,
        path: '/interact/chat',
        queryParameters: queryParams,
      );

      final headers = await _buildHeaders();

_chatDebugLog('[ChatService] Greeting request - URL: ${uri.toString()}');
_chatDebugLog('[ChatService] Greeting request - Headers: $headers');
_chatDebugLog('[ChatService] Greeting request - Query params: $queryParams');

      // Retry mechanism for greeting
      http.Response? response;
      int retryCount = 0;
      const maxRetries = 2;

      while (retryCount < maxRetries) {
        try {
          response = await http
              .post(
            uri,
            headers: headers,
          )
              .timeout(
            const Duration(seconds: 15), // Increased timeout for greeting
            onTimeout: () {
        _chatDebugLog(
                  '[ChatService] Greeting request timeout after 15 seconds (attempt ${retryCount + 1})');
              throw Exception('Greeting timeout');
            },
          );
          break; // Success, exit retry loop
        } catch (e) {
          retryCount++;
          if (retryCount >= maxRetries) {
      _chatDebugLog('[ChatService] All greeting retry attempts failed');
            rethrow; // Re-throw the last error
          }
    _chatDebugLog(
              '[ChatService] Greeting retry attempt $retryCount/$maxRetries after error: $e');
          await Future.delayed(
              Duration(seconds: retryCount * 2)); // Exponential backoff
        }
      }

      if (response == null) {
  _chatDebugLog(
            '[ChatService] Failed to get greeting response after $maxRetries attempts');
        return 'BACKEND_UNAVAILABLE';
      }

_chatDebugLog('[ChatService] Greeting response - Status: ${response.statusCode}');
_chatDebugLog('[ChatService] Greeting response - Body: ${response.body}');

      if (response.statusCode == 200) {
        final body = jsonDecode(response.body);

        // Safe parsing - handle optional fields
        final message = body['message'];
        final userId = body['user_id'] as int?;

  _chatDebugLog('[ChatService] Greeting success - message received from backend');
  _chatDebugLog(
            '[ChatService] Message length: ${message?.toString().length ?? 0}');
  _chatDebugLog('[ChatService] User ID: $userId');

        if (message != null && message.toString().isNotEmpty) {
          // Return message with user_id if available (for anonymous users)
          if (userId != null) {
            return 'USER_ID:$userId|MESSAGE:${message.toString()}';
          }
          return message.toString();
        } else {
    _chatDebugLog(
              '[ChatService] Warning: Backend returned empty message in greeting');
        }
      } else {
        // Log error details for debugging
  _chatDebugLog('[ChatService] Greeting failed: Status ${response.statusCode}');
        try {
          final errorBody = jsonDecode(response.body);
    _chatDebugLog('[ChatService] Error body: $errorBody');
        } catch (_) {
    _chatDebugLog('[ChatService] Error body (raw): ${response.body}');
        }
      }

      // If 401/404, user not registered yet - that's okay, use fallback
      // If other error, also use fallback
      return null;
    } catch (e) {
      // Any error - return BACKEND_UNAVAILABLE to show error message
_chatDebugLog('[ChatService] Greeting error: $e');
_chatDebugLog('[ChatService] Error type: ${e.runtimeType}');

      // Check for connection errors
      final errorString = e.toString().toLowerCase();
      if (errorString.contains('timeout') ||
          errorString.contains('connection refused') ||
          errorString.contains('failed host lookup') ||
          errorString.contains('network is unreachable') ||
          errorString.contains('socketexception') ||
          errorString.contains('connection reset') ||
          errorString.contains('no route to host')) {
        return 'BACKEND_UNAVAILABLE';
      }
_chatDebugLog('[ChatService] Full error: ${e.toString()}');
      // Return special marker to indicate backend unavailable
      return 'BACKEND_UNAVAILABLE';
    }
  }

  /// Setup onboarding - create user with username only (no password).
  /// Returns: (message, user_id, language) or (error, null, null).
  /// Backend expects only "name" in JSON body.
  Future<Map<String, dynamic>> setupOnboarding(
    String language, {
    required String name,
  }) async {
_chatDebugLog('[ChatService] ========== SETUP ONBOARDING START ==========');
_chatDebugLog('[ChatService] Name: "$name" (length: ${name.length})');
_chatDebugLog('[ChatService] Language: $language');
_chatDebugLog('[ChatService] Local mode: ${AppConfig.useLocalMode}');

    // ---------------- LOCAL MODE ----------------
    if (AppConfig.useLocalMode) {
_chatDebugLog('[ChatService] Using local mode - returning mock response');
      return {
        'message': 'Welcome! This is local mode.',
        'user_id': null,
        'language': language,
      };
    }

    // ---------------- BACKEND MODE ----------------
    // STEP 2: Validate name (REQUIRED, non-empty)
    if (name.trim().isEmpty) {
_chatDebugLog('[ChatService] ❌ ERROR: Name is required and cannot be empty');
      return {
        'message': 'Name is required and cannot be empty',
        'user_id': null,
        'language': null,
      };
    }

    try {
      // STEP 2: Use JSON body (not query params)
      final uri = Uri.parse('${AppConfig.baseUrl}/interact/onboarding');
      final headers = await _buildHeaders();
      
      // Backend onboarding: username only (no password)
      final payload = {
        'name': name.trim(),
      };

_chatDebugLog('[ChatService] Request URL: ${uri.toString()}');
_chatDebugLog('[ChatService] Request payload: $payload');
_chatDebugLog('[ChatService] Request headers: $headers');

      final response = await http
          .post(
        uri,
        headers: {
          ...headers,
          'Content-Type': 'application/json', // STEP 2: JSON body
        },
        body: jsonEncode(payload), // STEP 2: JSON body
      )
          .timeout(
        const Duration(seconds: 30), // Increased timeout
        onTimeout: () {
    _chatDebugLog('[ChatService] ❌ Request timeout after 30 seconds');
          throw Exception('Onboarding timeout');
        },
      );

_chatDebugLog('[ChatService] ========== RESPONSE RECEIVED ==========');
_chatDebugLog('[ChatService] Status code: ${response.statusCode}');
_chatDebugLog('[ChatService] Response body: ${response.body}');
_chatDebugLog('[ChatService] Response headers: ${response.headers}');

      if (response.statusCode == 200) {
        try {
          // ============================================
          // STEP 5: LOGGING (IMPORTANT)
          // ============================================
          // Add debug logging for onboarding response:
          // - full response body
          // - extracted user_id
          // ============================================
    _chatDebugLog('[ChatService] ===== RAW RESPONSE (200) =====');
    _chatDebugLog('[ChatService] Response body (raw): ${response.body}');
    _chatDebugLog('[ChatService] Response body length: ${response.body.length}');
          
          final body = jsonDecode(response.body);
    _chatDebugLog('[ChatService] ===== PARSED RESPONSE =====');
    _chatDebugLog('[ChatService] Parsed response body: $body');
    _chatDebugLog('[ChatService] Response type: ${body.runtimeType}');
    _chatDebugLog('[ChatService] Response keys: ${body.keys.toList()}');

          // Check if user_id exists in response
          if (!body.containsKey('user_id')) {
      _chatDebugLog('[ChatService] ⚠️ WARNING: user_id not found in response body');
      _chatDebugLog('[ChatService] Response body keys: ${body.keys.toList()}');
      _chatDebugLog('[ChatService] This indicates backend response format issue');
          }

          final userId = body['user_id'];
    _chatDebugLog('[ChatService] ===== USER_ID EXTRACTION =====');
    _chatDebugLog('[ChatService] user_id from body: $userId');
    _chatDebugLog('[ChatService] user_id type: ${userId?.runtimeType}');
    _chatDebugLog('[ChatService] user_id is null: ${userId == null}');
    _chatDebugLog('[ChatService] message: ${body['message']}');
    _chatDebugLog('[ChatService] language: ${body['language']}');

          // Handle both int and string user_id
          int? userIdInt;
          if (userId == null) {
      _chatDebugLog('[ChatService] ⚠️ WARNING: user_id is null in response');
      _chatDebugLog('[ChatService] This means registration FAILED on backend');
            userIdInt = null;
          } else if (userId is int) {
            userIdInt = userId;
      _chatDebugLog('[ChatService] ✅ user_id is int: $userIdInt');
          } else if (userId is String) {
            userIdInt = int.tryParse(userId);
            if (userIdInt == null) {
        _chatDebugLog('[ChatService] ⚠️ WARNING: Failed to parse user_id string: "$userId"');
            } else {
        _chatDebugLog('[ChatService] ✅ user_id is string, parsed: $userIdInt');
            }
          } else {
            userIdInt = int.tryParse(userId.toString());
            if (userIdInt == null) {
        _chatDebugLog('[ChatService] ⚠️ WARNING: Failed to parse user_id from type ${userId.runtimeType}: $userId');
            } else {
        _chatDebugLog('[ChatService] ✅ user_id is other type, converted: $userIdInt');
            }
          }

    _chatDebugLog('[ChatService] ===== FINAL USER_ID =====');
    _chatDebugLog('[ChatService] Final user_id: $userIdInt');
    _chatDebugLog('[ChatService] Final user_id is null: ${userIdInt == null}');
    _chatDebugLog('[ChatService] ===== END SUCCESS RESPONSE =====');

          // ============================================
          // STEP 1: FIX ONBOARDING SUCCESS CONDITION
          // ============================================
          // SUCCESS if and only if: user_id exists and is not null
          // FAILURE only if: HTTP error OR user_id is missing
          // DO NOT check: success flag, message content, chat response, GPT availability
          // ============================================
          
          if (userIdInt == null) {
      _chatDebugLog('[ChatService] ❌ ERROR: user_id is null after parsing');
      _chatDebugLog('[ChatService] This indicates registration FAILED on backend');
      _chatDebugLog('[ChatService] Response body: $body');
            return {
              'message': body['message']?.toString() ??
                  'Server response missing user_id. Please try again.',
              'user_id': null,
              'language': body['language']?.toString() ?? language,
            };
          }

          // ============================================
          // STEP 2: DECOUPLE ONBOARDING FROM CHAT
          // ============================================
          // Registration is SUCCESSFUL - return user_id immediately
          // Message content (even if it contains chat/GPT errors) does NOT affect registration success
          // ============================================
          
    _chatDebugLog('[ChatService] ✅ Registration SUCCESSFUL - user_id: $userIdInt');
    _chatDebugLog('[ChatService] Returning success response (message may contain chat errors, but registration succeeded)');
          
          return {
            'message': body['message']?.toString() ?? '',
            'user_id': userIdInt,
            'language': body['language']?.toString() ?? language,
          };
        } catch (e, stackTrace) {
    _chatDebugLog('[ChatService] ===== PARSE ERROR =====');
    _chatDebugLog('[ChatService] ERROR parsing response body: $e');
    _chatDebugLog('[ChatService] Stack trace: $stackTrace');
    _chatDebugLog('[ChatService] Response body (raw): ${response.body}');
    _chatDebugLog('[ChatService] Response status: ${response.statusCode}');
    _chatDebugLog('[ChatService] ===== END PARSE ERROR =====');
          return {
            'message': 'Error parsing server response. Please try again.',
            'user_id': null,
            'language': null,
          };
        }
      }

      // Parse error message - provide user-friendly messages
_chatDebugLog('[ChatService] ===== ERROR RESPONSE =====');
_chatDebugLog('[ChatService] Status code: ${response.statusCode}');
_chatDebugLog('[ChatService] Response body: ${response.body}');
_chatDebugLog('[ChatService] Response headers: ${response.headers}');

      String errorMessage = 'Error creating account. Please try again.';

      try {
        final errorBody = jsonDecode(response.body);
  _chatDebugLog('[ChatService] Error body parsed: $errorBody');

        // Try to get detail from error body
        final detail = errorBody['detail']?.toString() ??
            errorBody['message']?.toString() ??
            errorBody['error']?.toString() ??
            '';

  _chatDebugLog('[ChatService] Error detail extracted: $detail');

        // Use backend error detail if available
        if (detail.isNotEmpty) {
          errorMessage = detail;
    _chatDebugLog('[ChatService] Using backend error detail: $errorMessage');
        } else {
          // Map status codes to user-friendly messages
          switch (response.statusCode) {
            case 400:
              errorMessage =
                  'Invalid request. Please check your password (minimum 6 characters).';
              break;
            case 401:
              errorMessage = 'Authentication failed. Please try again.';
              break;
            case 404:
              errorMessage = 'Service not found. Please contact support.';
              break;
            case 422:
              errorMessage = 'Validation error. Please check your input.';
              break;
            case 500:
              errorMessage = 'Server error. Please try again later.';
              break;
            case 503:
              errorMessage =
                  'Service temporarily unavailable. Please try again later.';
              break;
            default:
              errorMessage = 'Registration failed. Please try again.';
          }
    _chatDebugLog(
              '[ChatService] Using status code based error message: $errorMessage');
        }
      } catch (parseError) {
  _chatDebugLog('[ChatService] ⚠️ Could not parse error body: $parseError');
  _chatDebugLog('[ChatService] Raw response body: ${response.body}');

        // If can't parse error body, use status code
        switch (response.statusCode) {
          case 400:
            errorMessage =
                'Invalid request. Please check your password (minimum 6 characters).';
            break;
          case 500:
            errorMessage = 'Server error. Please try again later.';
            break;
          case 503:
            errorMessage =
                'Service temporarily unavailable. Please try again later.';
            break;
          default:
            errorMessage = 'Registration failed. Please try again.';
        }
  _chatDebugLog('[ChatService] Using fallback error message: $errorMessage');
      }

_chatDebugLog('[ChatService] Final error message: $errorMessage');
_chatDebugLog('[ChatService] ===== END ERROR RESPONSE =====');
      return {
        'message': errorMessage,
        'user_id': null,
        'language': null,
      };
    } catch (e) {
_chatDebugLog('[ChatService] Onboarding exception: $e');
_chatDebugLog('[ChatService] Exception type: ${e.runtimeType}');

      // Provide user-friendly error messages based on exception type
      String errorMessage;
      final errorString = e.toString().toLowerCase();

      if (errorString.contains('timeout')) {
        errorMessage =
            'Connection timeout. Please check your internet connection and try again.';
      } else if (errorString.contains('connection refused') ||
          errorString.contains('failed host lookup') ||
          errorString.contains('socketexception')) {
        errorMessage =
            'Cannot connect to server. Please check your internet connection and try again.';
      } else if (errorString.contains('network')) {
        errorMessage =
            'Network error. Please check your internet connection and try again.';
      } else {
        errorMessage = 'Registration failed. Please try again.';
      }

      return {
        'message': errorMessage,
        'user_id': null,
        'language': null,
      };
    }
  }

  /// Register user with backend (onboarding) - DEPRECATED, use setupOnboarding
  Future<Map<String, dynamic>> registerUser(
    String userName,
    String language, {
    int? existingUserId,
  }) async {
    final result = await setupOnboarding(language, name: userName);
    return {
      'message': result['message'],
      'user_id': result['user_id'],
    };
  }

  /// Send message to backend or mock
  /// Returns response or 'SECURITY_CHECK_REQUIRED' if suspicious behavior detected
  Future<String> sendMessage(
    String userMessage, {
    String? userName,
    String? userPassword,
    String? language, // Language from ChatController (currentLanguage)
    int?
        userId, // CRITICAL: user_id from previous response to maintain conversation continuity
  }) async {
    // ---------------- LOCAL MODE ----------------
    if (AppConfig.useLocalMode) {
      await Future.delayed(
        Duration(milliseconds: 400 + Random().nextInt(600)),
      );
      return _mockReply(userMessage);
    }

    // ---------------- BACKEND MODE ----------------
    // Backend ChatRequest: JSON body { "user_id": int, "message": string } only.
    try {
      if (userMessage.trim().isEmpty) {
        return 'NETWORK_ERROR: Message cannot be empty';
      }
      if (userId == null || userId <= 0) {
        return 'VALIDATION_ERROR: user_id is required and must be a positive integer.';
      }

      final request = InteractRequest(
        userId: userId,
        message: userMessage.trim(),
      );
      final bodyJson = request.toJson();

      final baseUri = Uri.parse(AppConfig.baseUrl);
      final uri = Uri(
        scheme: baseUri.scheme,
        host: baseUri.host,
        port: baseUri.port,
        path: '/interact/chat',
      );

      // Safe debug log: no secrets
_chatDebugLog('[ChatService] ===== SENDING TO BACKEND =====');
_chatDebugLog('[ChatService] endpoint: ${uri.toString()}');
_chatDebugLog('[ChatService] payload keys: ${bodyJson.keys.toList()}');

      ChatRepositoryResult? result;
      int retryCount = 0;
      const maxRetries = 3;

      while (retryCount < maxRetries) {
        try {
          result = await sendChat(request);
          break;
        } catch (e) {
          retryCount++;
          if (retryCount >= maxRetries) {
      _chatDebugLog('[ChatService] All retry attempts failed');
            rethrow;
          }
    _chatDebugLog(
              '[ChatService] Retry attempt $retryCount/$maxRetries after error: $e');
          await Future.delayed(
              Duration(seconds: retryCount * 2));
        }
      }

      if (result == null) {
        throw Exception('Failed to get response after $maxRetries attempts');
      }

_chatDebugLog('[ChatService] ===== BACKEND RESPONSE =====');
_chatDebugLog('[ChatService] Status: ${result.statusCode}');
_chatDebugLog('[ChatService] Response body: ${result.body}');

      // Handle 422 (payload mismatch) with debug dump and user-friendly message
      if (result.statusCode == 422) {
        String detail = 'Validation error';
        try {
          final err = jsonDecode(result.body);
          if (err is Map) {
            final d = err['detail'];
            if (d is String) {
              detail = d;
            } else if (d is List && d.isNotEmpty) {
              final e = d.first;
              detail = (e is Map && e['msg'] != null)
                  ? e['msg'].toString()
                  : e.toString();
            }
          }
        } catch (_) {}
  _chatDebugLog('[ChatService] 422: endpoint=${uri.toString()} payload_keys=${bodyJson.keys.toList()} response=$detail');
        ChatLastErrorDump.set(
          endpoint: uri.toString(),
          payloadKeys: bodyJson.keys.map((e) => e.toString()).toList(),
          responseMessage: detail,
          statusCode: 422,
        );
        return 'REQUEST_FORMAT_ERROR: Request format issue. Please try again.';
      }

      // Handle 502 Bad Gateway (GPT failure) FIRST
      if (result.statusCode == 502) {
  _chatDebugLog('[ChatService] ❌ 502 Bad Gateway - GPT service error');
        try {
          final errorBody = jsonDecode(result.body);
          final errorDetail =
              errorBody['detail'] ?? errorBody['error'] ?? 'GPT service error';
    _chatDebugLog('[ChatService] GPT error detail: $errorDetail');
          return 'GPT_ERROR: $errorDetail';
        } catch (parseError) {
    _chatDebugLog('[ChatService] Could not parse 502 error body: $parseError');
          return 'GPT_ERROR: GPT service is unavailable. Please try again.';
        }
      }

      if (result.statusCode == 200) {
  _chatDebugLog('[ChatService] ✅ SUCCESS - Backend responded');
      } else {
  _chatDebugLog('[ChatService] ❌ ERROR - Status ${result.statusCode}');
  _chatDebugLog('[ChatService] Response body: ${result.body}');

        // Parse error response to get real backend error message
        try {
          final errorBody = jsonDecode(result.body);
          final errorDetail = errorBody.get('detail') ??
              errorBody.get('message') ??
              'Unknown error';
    _chatDebugLog('[ChatService] Backend error detail: $errorDetail');

          // Return structured error message from backend
          if (result.statusCode == 400) {
            return 'VALIDATION_ERROR: $errorDetail';
          } else if (result.statusCode == 404) {
            return 'USER_NOT_FOUND: $errorDetail';
          } else if (result.statusCode >= 500) {
            return 'SERVER_ERROR: $errorDetail';
          } else {
            return 'ERROR_${result.statusCode}: $errorDetail';
          }
        } catch (parseError) {
    _chatDebugLog('[ChatService] Could not parse error body: $parseError');
          if (result.statusCode == 400) {
            return 'VALIDATION_ERROR: Invalid request. Please check your input.';
          } else if (result.statusCode == 404) {
            return 'USER_NOT_FOUND: User not found. Please check your user_id.';
          } else {
            return 'ERROR_${result.statusCode}: Server returned error status ${result.statusCode}';
          }
        }
      }

      if (result.statusCode == 200) {
        final body = jsonDecode(result.body);

  _chatDebugLog('[ChatService] Response body keys: ${body.keys.toList()}');
  _chatDebugLog('[ChatService] Response body: $body');

        // Check for security flag in response (backend AI detected suspicious behavior)
        if (body['requires_security_check'] == true) {
    _chatDebugLog('[ChatService] ⚠️ Security check required');
          return 'SECURITY_CHECK_REQUIRED';
        }

        // Backend returns 'message' field, 'user_id' (for anonymous users), and 'detected_name' (if name detected)
        final message = body['message']?.toString() ?? '';
        final userId = body['user_id'] as int?;
        final detectedName = body['detected_name']?.toString();

  _chatDebugLog('[ChatService] Parsed message: "$message"');
  _chatDebugLog('[ChatService] Parsed user_id: $userId');
  _chatDebugLog('[ChatService] Parsed detected_name: $detectedName');

        if (message.isEmpty) {
    _chatDebugLog('[ChatService] ⚠️ WARNING: Backend returned empty message!');
    _chatDebugLog('[ChatService] Full response body: $body');
        }

        // Build response string with all data
        String responseString = message;

        // Add user_id if available (for anonymous users)
        if (userId != null) {
          responseString = 'USER_ID:$userId|$responseString';
        }

        // Add detected_name if available (to update UserProfile)
        if (detectedName != null && detectedName.isNotEmpty) {
          responseString = 'DETECTED_NAME:$detectedName|$responseString';
    _chatDebugLog(
              '[ChatService] ✅ Name detected from conversation: $detectedName');
        }

        return responseString;
      }

      if (result.statusCode == 401 || result.statusCode == 404) {
  _chatDebugLog('[ChatService] Auth error: Status ${result.statusCode}');
        // User not found - this is okay for new users, they can chat without registration
        // Backend will create user automatically or return error
        // But with anonymous users support, this shouldn't happen
        return 'AUTH_REQUIRED';
      }

      if (result.statusCode != 200) {
        try {
          final errorBody = jsonDecode(result.body);
    _chatDebugLog('[ChatService] Error ${result.statusCode}: $errorBody');
        } catch (_) {
    _chatDebugLog('[ChatService] Error ${result.statusCode}: ${result.body}');
        }
      }

      return 'SERVER_ERROR_${result.statusCode}';
    } catch (e) {
      // Better error handling for debugging
_chatDebugLog('[ChatService] ===== EXCEPTION CAUGHT =====');
_chatDebugLog('[ChatService] Exception type: ${e.runtimeType}');
_chatDebugLog('[ChatService] Exception message: $e');
_chatDebugLog('[ChatService] Stack trace: ${StackTrace.current}');

      final errorString = e.toString().toLowerCase();

      // Check for specific connection errors
      if (errorString.contains('timeout')) {
  _chatDebugLog(
            '[ChatService] ❌ Connection timeout - Server may be down or slow');
        return 'SERVER_CONNECTION_ERROR: Connection timeout. The server may be down or slow. Please try again.';
      } else if (errorString.contains('connection refused')) {
  _chatDebugLog(
            '[ChatService] ❌ Connection refused - Server is not accepting connections');
        return 'SERVER_CONNECTION_ERROR: Connection refused. The server may be down. Please check your internet connection and try again.';
      } else if (errorString.contains('failed host lookup') ||
          errorString.contains('name resolution')) {
  _chatDebugLog(
            '[ChatService] ❌ DNS resolution failed - Cannot resolve hostname');
        return 'SERVER_CONNECTION_ERROR: Cannot resolve server address. Please check your internet connection and try again.';
      } else if (errorString.contains('network is unreachable')) {
  _chatDebugLog('[ChatService] ❌ Network unreachable - No internet connection');
        return 'SERVER_CONNECTION_ERROR: Network unreachable. Please check your internet connection and try again.';
      } else if (errorString.contains('socketexception') ||
          errorString.contains('socket')) {
  _chatDebugLog('[ChatService] ❌ Socket exception - Network error');
        return 'SERVER_CONNECTION_ERROR: Network error. Please check your internet connection and try again.';
      } else if (errorString.contains('connection reset')) {
  _chatDebugLog('[ChatService] ❌ Connection reset - Server closed connection');
        return 'SERVER_CONNECTION_ERROR: Connection reset. The server closed the connection. Please try again.';
      } else if (errorString.contains('no route to host')) {
  _chatDebugLog('[ChatService] ❌ No route to host - Cannot reach server');
        return 'SERVER_CONNECTION_ERROR: Cannot reach server. Please check your internet connection and try again.';
      }

_chatDebugLog('[ChatService] ❌ Unknown network error: $e');
      return 'NETWORK_ERROR: ${e.toString()}';
    }
  }

  /// Test backend connection (uses same JSON body shape as chat).
  Future<bool> testConnection() async {
    if (AppConfig.useLocalMode) {
      return false;
    }
    try {
      final baseUri = Uri.parse(AppConfig.baseUrl);
      final uri = Uri(
        scheme: baseUri.scheme,
        host: baseUri.host,
        port: baseUri.port,
        path: '/interact/chat',
      );
      final headers = await _buildHeaders();
      final body = jsonEncode(InteractRequest(userId: 1, message: '__CONNECTION_TEST__').toJson());
      final response = await http
          .post(uri, headers: headers, body: body)
          .timeout(const Duration(seconds: 5), onTimeout: () {
        throw Exception('Connection timeout');
      });
      return response.statusCode == 200 ||
          response.statusCode == 401 ||
          response.statusCode == 422 ||
          response.statusCode == 400 ||
          response.statusCode == 404;
    } catch (e) {
_chatDebugLog('[ChatService] Connection test failed: $e');
      return false;
    }
  }
}
