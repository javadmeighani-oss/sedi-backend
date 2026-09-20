import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../../core/health_subject/sedi_health_subject_controller.dart';
import '../../../../core/locale/sedi_locale_controller.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../data/models/chat_message.dart';
import '../../../../services/notifications/inbox_refresh_bus.dart';
import '../../../../services/notifications/notifications_service.dart';
import '../../../chat/presentation/widgets/message_bubble.dart';
import '../../../chat/state/chat_controller.dart';
import '../../../devices/presentation/pages/devices_page.dart';
import '../../../lifestyle/presentation/pages/lifestyle_page.dart';
import '../../../notifications/presentation/pages/notification_inbox_page.dart';

import '../../models/gate3_interaction_state.dart';
import '../gate3_localization.dart';
import '../gate3_composer_draft_bus.dart';
import '../widgets/gate3_composer.dart';
import '../widgets/gate3_main_icon_row.dart';
import '../widgets/gate3_return_to_latest_button.dart';
import '../widgets/gate3_subject_selector.dart';
import '../widgets/sedi_brain_orb.dart';
import '../widgets/sedi_horizontal_resonance_visualizer.dart';

class Gate3InteractivePage extends StatefulWidget {
  final String? initialMessage;
  /// Composer-only seed text. Never auto-sends; never inserts into transcript.
  final String? initialDraft;
  final bool fromNotification;
  final int? notificationId;

  const Gate3InteractivePage({
    super.key,
    this.initialMessage,
    this.initialDraft,
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
  final SediHealthSubjectController _subjects =
      SediHealthSubjectController.instance;
  final NotificationsService _notificationsService = NotificationsService();
  int _subjectGenSeen = -1;

  bool _composerListening = false;
  String? _composerDraftSeed;
  int _composerDraftToken = 0;

  DateTime? _lastBackPressTime;
  Timer? _backPressTimer;
  StreamSubscription<String>? _draftSub;

  /// Backend canonical unread SENT-history count; null = not loaded yet.
  int? _unreadNotificationCount;
  StreamSubscription<void>? _inboxRefreshSub;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _controller = ChatController();
    _controller.addListener(_onControllerChanged);
    _controller.addListener(_scrollToBottomOnNewMessage);
    _subjects.addListener(_onSubjectChanged);
    _inboxRefreshSub = InboxRefreshBus.instance.stream.listen((_) {
      _refreshUnreadBadge();
    });
    final seed = widget.initialDraft?.trim();
    if (seed != null && seed.isNotEmpty) {
      _composerDraftSeed = seed;
    }
    _draftSub = Gate3ComposerDraftBus.instance.stream.listen((draft) {
      if (!mounted) return;
      setState(() {
        _composerDraftSeed = draft;
        _composerDraftToken++;
      });
    });
    _refreshUnreadBadge();
    _subjects.loadAccessibleSubjects().then((_) {
      _syncChatSubject();
      _controller.initialize(
        initialMessage: widget.initialMessage,
        notificationId: widget.notificationId,
      );
    });
  }

  Future<void> _refreshUnreadBadge() async {
    final resp = await _notificationsService.fetchUnreadCount();
    if (!mounted) return;
    if (resp.ok) {
      setState(() => _unreadNotificationCount = resp.data ?? 0);
    } else {
      setState(() => _unreadNotificationCount = _unreadNotificationCount ?? 0);
    }
  }

  Future<void> _openNotificationsInbox() async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => const NotificationInboxPage(),
      ),
    );
    if (!mounted) return;
    await _refreshUnreadBadge();
  }

  void _syncChatSubject() {
    _controller.activeHealthSubjectId = _subjects.activeSubject?.id;
  }

  void _onSubjectChanged() {
    if (!mounted) return;
    if (_subjectGenSeen == _subjects.generation) {
      setState(() {});
      return;
    }
    _subjectGenSeen = _subjects.generation;
    // Invalidate chat transcript when subject switches — no stale leakage.
    _controller.messages.clear();
    _syncChatSubject();
    setState(() {});
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _refreshUnreadBadge();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _inboxRefreshSub?.cancel();
    _draftSub?.cancel();
    _backPressTimer?.cancel();
    _controller.removeListener(_onControllerChanged);
    _controller.removeListener(_scrollToBottomOnNewMessage);
    _subjects.removeListener(_onSubjectChanged);
    _scrollController.dispose();
    _controller.dispose();
    super.dispose();
  }

  void _onControllerChanged() {
    if (mounted) setState(() {});
  }

  Gate3Localization get _l10n =>
      Gate3Localization(SediLocaleController.instance.languageCode);

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

  /// Presentation-only: seed composer with historical user text.
  /// Does not mutate transcript; Send creates a NEW user message.
  void _editUserMessageAsNewDraft(String text) {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return;
    setState(() {
      _composerDraftSeed = trimmed;
      _composerDraftToken++;
    });
  }

  Gate3InteractionState _orbState() {
    if (_controller.isSpeaking) return Gate3InteractionState.speaking;
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
    // When pushed (e.g. Lifestyle → Chat), allow one-route pop back.
    // Root A3 (no previous route) keeps the existing double-back exit policy.
    final routeCanPop = ModalRoute.of(context)?.canPop ?? false;

    final content = PopScope(
      canPop: routeCanPop,
      onPopInvoked: (didPop) {
        if (didPop) return;
        _handleBackPress();
      },
      child: Scaffold(
        backgroundColor: Colors.white,
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
                    unreadNotificationCount: _unreadNotificationCount,
                    onLifestyle: () {
                      if (!_subjects.isActiveSelf) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(content: Text(l10n.lifestyleOtherUnavailable)),
                        );
                        return;
                      }
                      _goTo(const LifestylePage());
                    },
                    onGadgets: () => _goTo(const DevicesPage()),
                    onNotifications: _openNotificationsInbox,
                  ),
                ),
                Offstage(
                  offstage: true,
                  child: Gate3SubjectSelector(l10n: l10n),
                ),
                const SizedBox(height: 4),
                SediBrainOrb(
                  state: _orbState(),
                  lang: _controller.currentLanguage,
                ),
                const SizedBox(height: 6),
                SediHorizontalResonanceVisualizer(state: _orbState()),
                const SizedBox(height: 8),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
                    child: Container(
                      width: double.infinity,
                      decoration: BoxDecoration(
                        color: Colors.white,
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
                              key: ValueKey('gate3-composer-$_composerDraftToken'),
                              placeholder: l10n.composerPlaceholder,
                              lang: _controller.currentLanguage,
                              isRtl: isRtl,
                              initialText:
                                  _composerDraftSeed ?? widget.initialDraft,
                              onListeningChanged: (listening) {
                                if (!mounted) return;
                                if (_composerListening == listening) return;
                                WidgetsBinding.instance.addPostFrameCallback((_) {
                                  if (!mounted) return;
                                  if (_composerListening == listening) return;
                                  setState(
                                      () => _composerListening = listening);
                                });
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
                                _controller.stopVoiceRecording().then((path) {
                                  if (!mounted) return;
                                  if (path != null && kDebugMode) {
                                    debugPrint(
                                        '[Audio] recorded file: $path');
                                  }
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
    if (_controller.messages.isEmpty) {
      // Non-transcript empty presentation — never invent assistant/user dialogue.
      return ListView(
        controller: _scrollController,
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(16, 24, 16, 16),
        children: [
          const SizedBox(height: 48),
          Text(
            l10n.emptyConversationHint,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 14,
              height: 1.35,
              color: AppTheme.textSecondary.withOpacity(0.85),
              fontWeight: FontWeight.w400,
            ),
          ),
        ],
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
          onEdit: msg.isUser && msg.text.trim().isNotEmpty
              ? () => _editUserMessageAsNewDraft(msg.text)
              : null,
          editLabel: l10n.editMessage,
        );
      },
    );
  }
}
