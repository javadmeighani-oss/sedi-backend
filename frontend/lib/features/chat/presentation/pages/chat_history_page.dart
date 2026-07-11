import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../core/utils/user_profile_manager.dart';
import '../../../../data/dto/history_response.dart';
import '../../../../data/repositories/chat_repository.dart';
import '../../../gate3_interactive/presentation/gate3_localization.dart';

/// Displays chat history from GET /memory/history (daily / weekly / monthly / yearly).
class ChatHistoryPage extends StatefulWidget {
  /// App language (`fa` / `ar` / `en`). When omitted, loaded from saved profile.
  final String? lang;

  const ChatHistoryPage({super.key, this.lang});

  @override
  State<ChatHistoryPage> createState() => _ChatHistoryPageState();
}

class _ChatHistoryPageState extends State<ChatHistoryPage> {
  static const List<String> _groups = ['daily', 'weekly', 'monthly', 'yearly'];

  String _lang = 'en';
  int? _userId;
  String _selectedGroup = 'daily';
  bool _loading = true;
  bool _langReady = false;
  String? _error;
  HistoryResponse? _data;

  Gate3Localization get l10n => Gate3Localization(_lang);

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    var lang = widget.lang;
    final profile = await UserProfileManager.loadProfile();
    lang ??= profile.preferredLanguage.isNotEmpty
        ? profile.preferredLanguage
        : 'en';
    if (!mounted) return;
    setState(() {
      _lang = lang!;
      _langReady = true;
      _userId = profile.userId;
      _loading = true;
      _error = null;
    });
    if (_userId == null) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = l10n.historySignInRequired;
      });
      return;
    }
    await _fetch();
  }

  Future<void> _fetch() async {
    if (_userId == null) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final res = await fetchHistory(
        userId: _userId!,
        group: _selectedGroup,
        limit: 50,
        offset: 0,
      );
      if (!mounted) return;
      setState(() {
        _data = res;
        _loading = false;
        _error = null;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = l10n.historyGenericError;
        _data = null;
      });
    }
  }

  void _onGroupSelected(String group) {
    if (group == _selectedGroup) return;
    setState(() => _selectedGroup = group);
    _fetch();
  }

  String _groupLabel(String group) {
    switch (group) {
      case 'weekly':
        return l10n.historyWeekly;
      case 'monthly':
        return l10n.historyMonthly;
      case 'yearly':
        return l10n.historyYearly;
      case 'daily':
      default:
        return l10n.historyDaily;
    }
  }

  String _localizeDateGroupKey(String key) {
    final normalized = key.trim().toLowerCase();
    if (normalized == 'today') return l10n.historyToday;
    if (normalized == 'yesterday') return l10n.historyYesterday;
    return key;
  }

  String _timeFromCreatedAt(String createdAt) {
    if (createdAt.trim().isEmpty) return '--:--';
    final dt = DateTime.tryParse(createdAt);
    if (dt == null) return '--:--';
    final local = dt.toLocal();
    return '${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
  }

  String _preview(String text, [int maxLen = 60]) {
    if (text.isEmpty) return '—';
    final t = text.trim();
    if (t.length <= maxLen) return t;
    return '${t.substring(0, maxLen)}…';
  }

  @override
  Widget build(BuildContext context) {
    if (!_langReady) {
      return const Scaffold(
        body: Center(
          child: CircularProgressIndicator(color: AppTheme.primaryBlack),
        ),
      );
    }

    final textDirection =
        l10n.isRtl ? TextDirection.rtl : TextDirection.ltr;

    return Directionality(
      textDirection: textDirection,
      child: Scaffold(
        backgroundColor: AppTheme.backgroundWhite,
        appBar: AppBar(
          backgroundColor: AppTheme.backgroundWhite,
          foregroundColor: AppTheme.primaryBlack,
          elevation: 0,
          title: Text(l10n.history),
          centerTitle: false,
        ),
        body: SafeArea(
          top: false,
          child: Column(
            children: [
              Padding(
                padding:
                    const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                child: Align(
                  alignment: AlignmentDirectional.centerStart,
                  child: Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: _groups.map((g) {
                      final selected = _selectedGroup == g;
                      return FilterChip(
                        label: Text(_groupLabel(g)),
                        selected: selected,
                        onSelected: (_) => _onGroupSelected(g),
                        selectedColor:
                            AppTheme.pistachioGreen.withOpacity(0.3),
                        checkmarkColor: AppTheme.primaryBlack,
                      );
                    }).toList(),
                  ),
                ),
              ),
              Expanded(
                child: _loading
                    ? Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const CircularProgressIndicator(
                              color: AppTheme.primaryBlack,
                            ),
                            const SizedBox(height: 12),
                            Text(
                              l10n.historyLoading,
                              style: const TextStyle(
                                color: AppTheme.textSecondary,
                                fontSize: 14,
                              ),
                            ),
                          ],
                        ),
                      )
                    : _error != null
                        ? _buildError()
                        : _data == null || _data!.items.isEmpty
                            ? _buildEmpty()
                            : _buildList(),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                child: Align(
                  alignment: AlignmentDirectional.centerStart,
                  child: Tooltip(
                    message: l10n.historyBackToChat,
                    child: GestureDetector(
                      onTap: () => Navigator.pop(context),
                      child: Container(
                        width: 40,
                        height: 40,
                        decoration: const BoxDecoration(
                          shape: BoxShape.circle,
                          color: AppTheme.primaryBlack,
                        ),
                        child: const Icon(
                          Icons.keyboard_arrow_down_rounded,
                          color: AppTheme.backgroundWhite,
                          size: 24,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildError() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              _error!,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: AppTheme.textSecondary,
                fontSize: 14,
              ),
            ),
            const SizedBox(height: 16),
            TextButton.icon(
              onPressed: _fetch,
              icon: const Icon(Icons.refresh, size: 20),
              label: Text(l10n.historyRetry),
              style: TextButton.styleFrom(
                foregroundColor: AppTheme.primaryBlack,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEmpty() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              l10n.historyEmptyTitle,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: AppTheme.textPrimary,
                fontSize: 16,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              l10n.historyEmptySubtitle,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: AppTheme.textSecondary,
                fontSize: 14,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildList() {
    final items = _data!.items;
    return ListView.builder(
      padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
      itemCount: items.length,
      itemBuilder: (context, index) {
        final group = items[index];
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(top: 12, bottom: 6),
              child: Text(
                _localizeDateGroupKey(group.key),
                style: const TextStyle(
                  color: AppTheme.textPrimary,
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            ...group.turns.map(
              (turn) => _TurnTile(
                turn: turn,
                timeStr: _timeFromCreatedAt(turn.createdAt),
                preview: _preview(turn.userMessage),
                isRtl: l10n.isRtl,
                onTap: () => _showTurnDialog(turn),
              ),
            ),
          ],
        );
      },
    );
  }

  void _showTurnDialog(HistoryTurnItem turn) {
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(_timeFromCreatedAt(turn.createdAt)),
        content: ConstrainedBox(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.of(ctx).size.height * 0.5,
          ),
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  l10n.historyYou,
                  style: const TextStyle(
                    fontWeight: FontWeight.w600,
                    fontSize: 12,
                  ),
                ),
                const SizedBox(height: 4),
                Text(turn.userMessage, style: const TextStyle(fontSize: 14)),
                const SizedBox(height: 12),
                Text(
                  l10n.historySedi,
                  style: const TextStyle(
                    fontWeight: FontWeight.w600,
                    fontSize: 12,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  turn.sediResponse ?? '—',
                  style: const TextStyle(fontSize: 14),
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text(l10n.close),
          ),
        ],
      ),
    );
  }
}

class _TurnTile extends StatelessWidget {
  final HistoryTurnItem turn;
  final String timeStr;
  final String preview;
  final bool isRtl;
  final VoidCallback onTap;

  const _TurnTile({
    required this.turn,
    required this.timeStr,
    required this.preview,
    required this.isRtl,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          textDirection: isRtl ? TextDirection.rtl : TextDirection.ltr,
          children: [
            SizedBox(
              width: 44,
              child: Text(
                timeStr,
                style: const TextStyle(
                  color: AppTheme.textSecondary,
                  fontSize: 13,
                ),
              ),
            ),
            Expanded(
              child: Text(
                preview,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: AppTheme.textPrimary,
                  fontSize: 14,
                ),
              ),
            ),
            const Icon(
              Icons.chevron_right,
              color: AppTheme.metalGrey,
              size: 20,
            ),
          ],
        ),
      ),
    );
  }
}
