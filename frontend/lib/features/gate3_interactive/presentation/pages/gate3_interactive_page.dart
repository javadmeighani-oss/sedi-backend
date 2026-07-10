import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../../core/auth/user_identity_service.dart';
import '../../../../core/navigation/app_gate_router.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../data/models/chat_message.dart';
import '../../../chat/presentation/pages/chat_history_page.dart';
import '../../../chat/presentation/widgets/message_bubble.dart';
import '../../../chat/state/chat_controller.dart';
import '../../../devices/presentation/pages/devices_page.dart';
import '../../../health/presentation/pages/vitals_page.dart';
import '../../../lifestyle/presentation/pages/lifestyle_page.dart';
import '../../../notification/data/notification_service.dart';
import '../../../gate4_notifications/presentation/pages/gate4_notifications_placeholder_page.dart';

import '../../models/gate3_interaction_state.dart';
import '../gate3_localization.dart';
import '../widgets/gate3_composer.dart';
import '../widgets/gate3_main_icon_row.dart';
import '../widgets/gate3_return_to_latest_button.dart';
import '../widgets/gate3_scroll_day_control.dart';
import '../widgets/gate3_settings_menu.dart';
import '../widgets/sedi_brain_orb.dart';

class Gate3InteractivePage extends StatefulWidget {
  final String? initialMessage;
  final bool fromNotification;
  final int? notificationId;

  const Gate3InteractivePage({
    super.key,
    this.initialMessage,
    this.fromNotification = false,
    this.notificationId,
  });

  @override
  State<Gate3InteractivePage> createState() => _Gate3InteractivePageState();
}

class _Gate3InteractivePageState extends State<Gate3InteractivePage>
    with WidgetsBindingObserver {
  late final ChatController _controller;
  final ScrollController _scrollController = ScrollController();
  final NotificationService _notificationService = NotificationService();

  int? _unreadCount;

  DateTime? _lastBackPressTime;
  Timer? _backPressTimer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _controller = ChatController();
    _controller.addListener(_onControllerChanged);
    _controller.addListener(_scrollToBottomOnNewMessage);
    _controller.initialize(initialMessage: widget.initialMessage);
    _refreshUnreadCount();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _backPressTimer?.cancel();
    _controller.removeListener(_onControllerChanged);
    _controller.removeListener(_scrollToBottomOnNewMessage);
    _scrollController.dispose();
    _controller.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _refreshUnreadCount();
    }
  }

  void _onControllerChanged() {
    if (mounted) setState(() {});
  }

  Gate3Localization get _l10n => Gate3Localization(_controller.currentLanguage);

  void _scrollToBottomOnNewMessage() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _scrollToBottom();
    });
  }

  void _scrollToBottom() {
    if (_scrollController.hasClients) {
      _scrollController.animateTo(
        0,
        duration: const Duration(milliseconds: 280),
        curve: Curves.easeOutCubic,
      );
    }
  }

  Future<void> _refreshUnreadCount() async {
    final userId = await UserIdentityService.resolveUserId();
    if (userId == null) {
      if (!mounted) return;
      AppGateRouter.goToLogin(context);
      return;
    }
    final resp = await _notificationService.fetchUnreadList(userId: userId);
    if (!mounted) return;
    if (resp['ok'] == true) {
      setState(() => _unreadCount = NotificationService.parseUnreadCount(resp));
    } else {
      setState(() => _unreadCount = _unreadCount ?? 0);
    }
  }

  bool _handleBackPress() {
    final now = DateTime.now();
    if (_lastBackPressTime == null ||
        now.difference(_lastBackPressTime!) > const Duration(seconds: 2)) {
      _lastBackPressTime = now;
      _backPressTimer?.cancel();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(_l10n.pressBackAgainToExit),
          duration: const Duration(seconds: 2),
          backgroundColor: AppTheme.primaryBlack.withOpacity(0.8),
          behavior: SnackBarBehavior.floating,
          margin: const EdgeInsets.only(bottom: 100, left: 16, right: 16),
        ),
      );
      _backPressTimer = Timer(const Duration(seconds: 2), () {
        if (mounted) setState(() => _lastBackPressTime = null);
      });
      return false;
    }
    _backPressTimer?.cancel();
    SystemNavigator.pop();
    return true;
  }

  void _handleSendText(String text) {
    _controller.sendUserMessage(text);
  }

  Gate3InteractionState _orbState() {
    if (_controller.isThinking) return Gate3InteractionState.thinking;
    return Gate3InteractionState.idle;
  }

  void _goTo(Widget page) {
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => page)).then(
          (_) => _refreshUnreadCount(),
        );
  }

  List<ChatMessage> _sampleMessages(Gate3Localization l10n) {
    return [
      ChatMessage(
        text: l10n.sampleIntroAssistant1(),
        role: ChatRole.assistant,
      ),
      ChatMessage.user(
        text: l10n.sampleIntroUser1(),
        localId: 'sample-1',
        status: ChatMessageStatus.sent,
      ),
      ChatMessage(
        text: l10n.sampleIntroAssistant2(),
        role: ChatRole.assistant,
      ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final l10n = _l10n;
    final isRtl = l10n.isRtl;

    final content = PopScope(
      canPop: false,
      onPopInvoked: (didPop) {
        if (didPop) return;
        _handleBackPress();
      },
      child: Scaffold(
        backgroundColor: AppTheme.gate3PaleOliveBackground,
        resizeToAvoidBottomInset: true,
        body: SafeArea(
          child: Directionality(
            textDirection: isRtl ? TextDirection.rtl : TextDirection.ltr,
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 4, 16, 0),
                  child: Align(
                    alignment: AlignmentDirectional.centerStart,
                    child: Gate3SettingsMenu(lang: _controller.currentLanguage),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 6, 16, 4),
                  child: Gate3MainIconRow(
                    lang: _controller.currentLanguage,
                    unreadCount: _unreadCount,
                    onNotifications: () =>
                        _goTo(const Gate4NotificationsPlaceholderPage()),
                    onHealthCare: () => _goTo(const VitalsPage()),
                    onLifestyle: () => _goTo(const LifestylePage()),
                    onGadgets: () => _goTo(const DevicesPage()),
                    onHistory: () => _goTo(const ChatHistoryPage()),
                  ),
                ),
                const SizedBox(height: 2),
                SediBrainOrb(
                  state: _orbState(),
                  lang: _controller.currentLanguage,
                ),
                const SizedBox(height: 8),

                // Chat panel — taller footprint via reduced orb spacing above.
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
                    child: Container(
                      width: double.infinity,
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.55),
                        borderRadius: BorderRadius.circular(26),
                        border: Border.all(
                          color: AppTheme.borderInactive.withOpacity(0.22),
                        ),
                        boxShadow: const [
                          BoxShadow(
                            color: Color(0x12000000),
                            blurRadius: 18,
                            offset: Offset(0, 8),
                          ),
                        ],
                      ),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(26),
                        child: Stack(
                          children: [
                            Positioned.fill(
                              child: Padding(
                                padding:
                                    const EdgeInsets.fromLTRB(10, 12, 42, 108),
                                child: _buildMessages(l10n),
                              ),
                            ),
                            Positioned(
                              top: 12,
                              right: 8,
                              bottom: 108,
                              child: Gate3ScrollDayControl(
                                scrollController: _scrollController,
                              ),
                            ),
                            PositionedDirectional(
                              start: 14,
                              bottom: 104,
                              child: Gate3ReturnToLatestButton(
                                scrollController: _scrollController,
                                onTap: _scrollToBottom,
                                tooltip: l10n.returnToLatest,
                              ),
                            ),
                            PositionedDirectional(
                              start: 0,
                              end: 0,
                              bottom: 0,
                              child: Gate3Composer(
                                placeholder: l10n.composerPlaceholder,
                                isRtl: isRtl,
                                onSendText: _handleSendText,
                                onStartRecording: () {
                                  _controller.startVoiceRecording().then((ok) {
                                    if (!mounted) return;
                                    if (ok == false) {
                                      ScaffoldMessenger.of(context).showSnackBar(
                                        SnackBar(
                                          content: Text(
                                            l10n.microphonePermissionRequired,
                                          ),
                                          behavior: SnackBarBehavior.floating,
                                          margin: const EdgeInsets.only(
                                            bottom: 100,
                                            left: 16,
                                            right: 16,
                                          ),
                                        ),
                                      );
                                    }
                                  });
                                },
                                onStopRecordingAndSend: () {
                                  _controller.stopVoiceRecording().then((path) {
                                    if (!mounted) return;
                                    if (path != null && kDebugMode) {
                                      debugPrint(
                                          '[Audio] recorded file: $path');
                                    }
                                  });
                                },
                                isRecording: _controller.isRecording,
                                recordingTime:
                                    _controller.recordingTimeFormatted,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );

    return content;
  }

  Widget _buildMessages(Gate3Localization l10n) {
    if (_controller.messages.isEmpty) {
      final sample = _sampleMessages(l10n);
      return ListView.builder(
        controller: _scrollController,
        reverse: true,
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.only(top: 6, bottom: 8),
        itemCount: sample.length,
        itemBuilder: (context, index) {
          final reverseIndex = sample.length - 1 - index;
          final msg = sample[reverseIndex];
          return MessageBubble(
            message: msg.text,
            isSedi: msg.isSedi,
          );
        },
      );
    }

    return ListView.builder(
      controller: _scrollController,
      reverse: true,
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.only(top: 6, bottom: 8),
      itemCount: _controller.messages.length + (_controller.isThinking ? 1 : 0),
      itemBuilder: (context, index) {
        if (_controller.isThinking && index == 0) {
          return const MessageBubble(
            message: '...',
            isSedi: true,
            showTyping: true,
          );
        }
        final effectiveIndex = _controller.isThinking ? index - 1 : index;
        final reverseIndex =
            _controller.messages.length - 1 - effectiveIndex;
        final msg = _controller.messages[reverseIndex];
        return MessageBubble(
          message: msg.text,
          isSedi: msg.isSedi,
          isFailed: msg.isUser && msg.status == ChatMessageStatus.failed,
          onRetry: msg.isUser && msg.status == ChatMessageStatus.failed
              ? () => _controller.retryFailedMessage(msg.localId)
              : null,
        );
      },
    );
  }
}
