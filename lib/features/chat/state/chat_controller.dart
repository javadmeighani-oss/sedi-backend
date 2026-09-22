/// ============================================
/// ChatController - Display Layer Only
/// ============================================
///
/// RESPONSIBILITY:
/// - فقط نمایش پاسخ‌های backend
/// - ارسال پیام کاربر به backend
/// - هیچ تصمیم‌گیری یا logic ندارد
/// - همه متن‌ها از backend می‌آیند
/// ============================================

import '../../../core/locale/sedi_locale_controller.dart';
import '../../../core/utils/user_profile_manager.dart';
import '../../../data/dto/chat/chat_send_response.dart';
import '../../../data/dto/lifestyle_summary_response.dart';
import '../../../data/models/chat_message.dart';
import '../../../data/models/user_profile.dart';
import '../../../data/repositories/lifestyle_repository.dart';
import '../../../services/chat/chat_service.dart' as v1chat;
import '../../../services/chat/chat_stream_client.dart';
import 'package:flutter/foundation.dart';
import '../../../services/audio/audio_recorder_service.dart';

enum ConversationState {
  initializing, // در حال دریافت greeting از backend
  chatting, // مکالمه عادی
}

class ChatController extends ChangeNotifier {
  // ===============================
  // Animation States (for SediHeader)
  // ===============================

  bool isThinking = false;
  bool isSpeaking = false;
  bool isAlert = false;

  // ===============================
  // Language & Conversation State
  // ===============================

  String currentLanguage = 'en';
  ConversationState conversationState = ConversationState.initializing;

  // User Profile
  UserProfile _userProfile = UserProfile();

  // ===============================
  // Voice Recording
  // ===============================

  bool isRecording = false;
  int recordingDuration = 0;

  // ===============================
  // Messages
  // ===============================

  final List<ChatMessage> messages = [];

  final v1chat.ChatService _chatService = v1chat.ChatService();
  final ChatStreamClient _streamClient = ChatStreamClient();
  final LifestyleRepository _lifestyleRepo = LifestyleRepository();
  final AudioRecorderService _audioRecorder = AudioRecorderService();
  bool _initialized = false;
  int? sourceNotificationId;
  int? activeHealthSubjectId;

  /// Stage 17.2: Cached lifestyle summary (in-memory, session only)
  LifestyleSummaryResponse? _cachedLifestyleSummary;
  bool _lifestyleSummaryLoading = false;
  String? _lifestyleSummaryError;

  LifestyleSummaryResponse? get cachedLifestyleSummary =>
      _cachedLifestyleSummary;
  bool get lifestyleSummaryLoading => _lifestyleSummaryLoading;
  String? get lifestyleSummaryError => _lifestyleSummaryError;

  /// Fetch lifestyle summary. Uses cache unless [forceRefresh] or no cache.
  Future<void> fetchLifestyleSummary({bool forceRefresh = false}) async {
    if (!forceRefresh && _cachedLifestyleSummary != null) {
      notifyListeners();
      return;
    }
    final userId = _userProfile.userId;
    if (userId == null) {
      _lifestyleSummaryError = 'Please sign in to see lifestyle summary';
      notifyListeners();
      return;
    }
    _lifestyleSummaryLoading = true;
    _lifestyleSummaryError = null;
    notifyListeners();
    try {
      final res = await _lifestyleRepo.fetchLifestyleSummary(
        userId: userId,
        lang: currentLanguage,
      );
      if (res.ok && res.data != null) {
        _cachedLifestyleSummary = res.data;
        _lifestyleSummaryError = null;
      } else {
        _lifestyleSummaryError = res.error?.message ?? 'Failed to load summary';
      }
    } catch (e) {
      _lifestyleSummaryError = e.toString().replaceFirst('Exception: ', '');
    } finally {
      _lifestyleSummaryLoading = false;
      notifyListeners();
    }
  }

  // ===============================
  // Initialization
  // ===============================

  Future<void> initialize({String? initialMessage, int? notificationId}) async {
    if (_initialized) {
      print('[ChatController] ⚠️ Already initialized, skipping');
      return;
    }
    _initialized = true;
    sourceNotificationId = notificationId;

    print('[ChatController] ========== INITIALIZE START ==========');

    _userProfile = await UserProfileManager.loadProfile();
    currentLanguage = SediLocaleController.instance.languageCode;

    conversationState = ConversationState.initializing;
    notifyListeners();

    if (initialMessage != null) {
      conversationState = ConversationState.chatting;
      notifyListeners();
      if (initialMessage.isNotEmpty) {
        _addSediMessage(initialMessage);
      }
      return;
    }

    try {
      final open = await _chatService.openSession(language: currentLanguage);
      if (open.ok && open.data != null) {
        final data = open.data!;
        if (data.language.isNotEmpty) {
          currentLanguage = data.language;
          await SediLocaleController.instance.reconcileFromBackendConfirmed(
            data.language,
          );
        }
        final text = data.message.trim().isNotEmpty
            ? data.message
            : (data.proactiveOpener ?? '').trim();
        if (text.isNotEmpty) {
          _addSediMessage(text);
        }
      }
    } catch (e) {
      if (kDebugMode) {
        debugPrint('[ChatController] session/open failed: $e');
      }
    }

    conversationState = ConversationState.chatting;
    notifyListeners();
  }

  // ===============================
  // User Text Message
  // ===============================

  /// Send user message to backend and display response
  /// NO frontend logic - backend decides everything
  Future<void> sendUserMessage(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return;
    final localId = DateTime.now().microsecondsSinceEpoch.toString();
    // Do not mutate Account.preferred_language from typed language.
    currentLanguage = SediLocaleController.instance.languageCode;

    messages.add(
      ChatMessage.user(
        text: trimmed,
        localId: localId,
        status: ChatMessageStatus.sending,
      ),
    );
    isThinking = true;
    isSpeaking = false;
    notifyListeners();

    final streamLocalId = 'sedi-stream-$localId';
    var streamStarted = false;

    try {
      final streamed = await _streamClient.sendStreaming(
        message: trimmed,
        language: currentLanguage,
        sourceNotificationId: sourceNotificationId,
        healthSubjectId: activeHealthSubjectId,
        onDelta: (delta) {
          if (!streamStarted) {
            streamStarted = true;
            isThinking = false;
            isSpeaking = true;
            messages.add(
              ChatMessage.assistant(text: delta, localId: streamLocalId),
            );
          } else {
            final idx =
                messages.indexWhere((m) => m.localId == streamLocalId);
            if (idx >= 0) {
              messages[idx] = ChatMessage.assistant(
                text: messages[idx].text + delta,
                localId: streamLocalId,
              );
            }
          }
          notifyListeners();
        },
      );

      if (streamed != null) {
        _setMessageStatus(localId, ChatMessageStatus.sent);
        if (!streamStarted && streamed.message.trim().isNotEmpty) {
          await _appendAssistantResponse(streamed);
        } else if (streamStarted && streamed.message.trim().isNotEmpty) {
          final idx = messages.indexWhere((m) => m.localId == streamLocalId);
          if (idx >= 0) {
            messages[idx] = ChatMessage.assistant(
              text: streamed.message,
              localId: streamLocalId,
            );
          }
        }
        isThinking = false;
        isSpeaking = false;
        notifyListeners();
        return;
      }
    } catch (e) {
      isSpeaking = false;
      if (kDebugMode) {
        debugPrint('[ChatController] stream failed, JSON fallback: $e');
      }
    }
    isSpeaking = false;

    final response = await _chatService.sendMessage(
      message: trimmed,
      language: currentLanguage,
      sourceNotificationId: sourceNotificationId,
      healthSubjectId: activeHealthSubjectId,
    );

    if (!response.ok || response.data == null) {
      _setMessageStatus(localId, ChatMessageStatus.failed);
      isThinking = false;
      isSpeaking = false;
      notifyListeners();
      return;
    }

    _setMessageStatus(localId, ChatMessageStatus.sent);
    await _appendAssistantResponse(response.data!);
  }

  Future<void> retryFailedMessage(String localId) async {
    final index = messages.indexWhere((m) => m.localId == localId);
    if (index < 0) return;
    final failed = messages[index];
    if (!failed.isUser || failed.status != ChatMessageStatus.failed) return;

    _setMessageStatus(localId, ChatMessageStatus.sending);
    isThinking = true;
    isSpeaking = false;
    notifyListeners();

    final response = await _chatService.sendMessage(
      message: failed.text,
      language: currentLanguage,
      sourceNotificationId: sourceNotificationId,
      healthSubjectId: activeHealthSubjectId,
    );
    if (!response.ok || response.data == null) {
      _setMessageStatus(localId, ChatMessageStatus.failed);
      isThinking = false;
      isSpeaking = false;
      notifyListeners();
      return;
    }

    _setMessageStatus(localId, ChatMessageStatus.sent);
    await _appendAssistantResponse(response.data!);
  }

  Future<void> _appendAssistantResponse(ChatSendResponse data) async {
    isSpeaking = false;
    if (data.userId != null && _userProfile.userId == null) {
      _userProfile = _userProfile.copyWith(userId: data.userId);
    }
    if (data.detectedName != null && data.detectedName!.trim().isNotEmpty) {
      _userProfile = _userProfile.copyWith(name: data.detectedName!.trim());
    }
    // Locale authority remains Account.preferred_language → SediLocaleController.
    // Do not mutate preferred_language from typed/chat response language alone.
    currentLanguage = SediLocaleController.instance.languageCode;
    _userProfile = _userProfile.copyWith(
      conversationCount: _userProfile.conversationCount + 1,
    );
    await UserProfileManager.saveProfile(_userProfile);

    if (data.message.trim().isNotEmpty) {
      _addSediMessage(data.message.trim());
    } else {
      isThinking = false;
      notifyListeners();
    }
  }

  void _setMessageStatus(String localId, ChatMessageStatus status) {
    final idx = messages.indexWhere((m) => m.localId == localId);
    if (idx < 0) return;
    messages[idx] = messages[idx].copyWith(status: status);
  }

  // ===============================
  // Sedi Message (Display Only)
  // ===============================

  void _addSediMessage(String text) {
    isThinking = false;
    isSpeaking = false;

    messages.add(
      ChatMessage(
        text: text,
        role: ChatRole.assistant,
      ),
    );

    notifyListeners();
  }

  /// Presentation-only Lifestyle/context starter. Never SPEAKING; never auto-send.
  void insertPresentationAssistantMessage(String text) {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return;
    isThinking = false;
    isSpeaking = false;
    messages.add(ChatMessage.assistant(text: trimmed));
    notifyListeners();
  }

  // ===============================
  // Voice Recording (Stage 24: MVP local file; no voice-to-text yet)
  // ===============================

  /// Returns true if recording started, false if permission denied or error.
  Future<bool> startVoiceRecording() async {
    try {
      final granted = await _audioRecorder.ensurePermission();
      if (!granted) return false;
      await _audioRecorder.start();
      isRecording = true;
      recordingDuration = 0;
      notifyListeners();
      _tickRecordingTimer();
      return true;
    } catch (e) {
      if (kDebugMode)
        debugPrint('[ChatController] startVoiceRecording error: $e');
      return false;
    }
  }

  /// Stops recording and returns the local file path, or null on error.
  Future<String?> stopVoiceRecording() async {
    try {
      final path = await _audioRecorder.stop();
      isRecording = false;
      notifyListeners();
      return path;
    } catch (e) {
      if (kDebugMode)
        debugPrint('[ChatController] stopVoiceRecording error: $e');
      isRecording = false;
      notifyListeners();
      return null;
    }
  }

  void _tickRecordingTimer() {
    Future.delayed(const Duration(seconds: 1), () {
      if (!isRecording) return;
      recordingDuration++;
      notifyListeners();
      _tickRecordingTimer();
    });
  }

  String get recordingTimeFormatted {
    final m = recordingDuration ~/ 60;
    final s = recordingDuration % 60;
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }

  // ===============================
  // Last message (UI helper)
  // ===============================

  ChatMessage? get lastMessage => messages.isEmpty ? null : messages.last;

  @override
  void dispose() {
    _streamClient.dispose();
    super.dispose();
  }
}
