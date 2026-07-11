import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../data/models/chat_message.dart';
import '../../../chat/presentation/widgets/message_bubble.dart';
import '../../../chat/state/chat_controller.dart';

import '../../models/gate3_interaction_state.dart';
import '../gate3_localization.dart';
import '../sections/gadgets/gate3_gadgets_page.dart';
import '../sections/health_care/gate3_health_care_page.dart';
import '../sections/lifestyle/gate3_lifestyle_overview_page.dart';
import '../sections/settings/gate3_settings_page.dart';
import '../widgets/gate3_composer.dart';
import '../widgets/gate3_main_icon_row.dart';
import '../widgets/gate3_return_to_latest_button.dart';
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

  bool _composerListening = false;

  DateTime? _lastBackPressTime;
  Timer? _backPressTimer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _controller = ChatController();
    _controller.addListener(_onControllerChanged);
    _controller.addListener(_scrollToBottomOnNewMessage);
    _controller.initialize(initialMessage: widget.initialMessage).then((_) {
      if (mounted) _scrollToBottom();
    });
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
    if (_controller.isRecording || _composerListening) {
      return Gate3InteractionState.listening;
    }
    return Gate3InteractionState.idle;
  }

  void _goTo(Widget page) {
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => page));
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
                  padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
                  child: Gate3MainIconRow(
                    lang: _controller.currentLanguage,
                    onSettings: () => _goTo(
                      Gate3SettingsPage(lang: _controller.currentLanguage),
                    ),
                    onHealthCare: () => _goTo(
                      Gate3HealthCarePage(lang: _controller.currentLanguage),
                    ),
                    onLifestyle: () => _goTo(
                      Gate3LifestyleOverviewPage(
                        lang: _controller.currentLanguage,
                      ),
                    ),
                    onGadgets: () => _goTo(
                      Gate3GadgetsPage(lang: _controller.currentLanguage),
                    ),
                  ),
                ),
                const SizedBox(height: 4),
                SediBrainOrb(
                  state: _orbState(),
                ),
                const SizedBox(height: 8),
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
                        child: Column(
                          children: [
                            Expanded(
                              child: Stack(
                                children: [
                                  Positioned.fill(
                                    child: Padding(
                                      padding: const EdgeInsets.fromLTRB(
                                        10,
                                        12,
                                        10,
                                        8,
                                      ),
                                      child: _buildMessages(l10n),
                                    ),
                                  ),
                                  Positioned(
                                    right: 12,
                                    bottom: 12,
                                    child: Gate3ReturnToLatestButton(
                                      scrollController: _scrollController,
                                      onTap: _scrollToBottom,
                                      tooltip: l10n.returnToLatest,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            Gate3Composer(
                              placeholder: l10n.composerPlaceholder,
                              lang: _controller.currentLanguage,
                              isRtl: isRtl,
                              onListeningChanged: (listening) {
                                if (_composerListening != listening) {
                                  setState(
                                      () => _composerListening = listening);
                                }
                              },
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
                                  } else {
                                    setState(() => _composerListening = true);
                                  }
                                });
                              },
                              onStopRecordingAndSend: () {
                                _controller.stopVoiceRecording().then((_) {
                                  if (!mounted) return;
                                  setState(() => _composerListening = false);
                                });
                              },
                              isRecording: _controller.isRecording,
                              recordingTime:
                                  _controller.recordingTimeFormatted,
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
    if (_controller.conversationState == ConversationState.initializing &&
        _controller.messages.isEmpty) {
      return const Center(
        child: SizedBox(
          width: 24,
          height: 24,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            color: AppTheme.gate2ButtonOlive,
          ),
        ),
      );
    }

    if (_controller.messages.isEmpty) {
      return const SizedBox.shrink();
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
