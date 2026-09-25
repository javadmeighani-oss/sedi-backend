import 'package:flutter/material.dart';

import '../../../../core/locale/calendar_date_math.dart';
import '../../../../core/locale/sedi_locale_controller.dart';
import '../../../../core/network/api_client.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../data/dto/history_response.dart';
import '../../../gate3_interactive/presentation/widgets/a3_destination_surface.dart';
import '../../../gate3_interactive/presentation/widgets/a3_page_app_bar.dart';
import '../lifestyle_l10n.dart';

class LifestyleHistoryPage extends StatefulWidget {
  const LifestyleHistoryPage({super.key});

  @override
  State<LifestyleHistoryPage> createState() => _LifestyleHistoryPageState();
}

class _LifestyleHistoryPageState extends State<LifestyleHistoryPage> {
  final _api = ApiClient();
  String _group = 'daily';
  HistoryResponse? _history;
  String? _summaryText;
  bool _loading = true;
  bool _summaryLoading = false;
  String? _error;
  String? _expandedKey;

  LifestyleL10n get _l10n =>
      LifestyleL10n(SediLocaleController.instance.languageCode);

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
      _history = null;
      _summaryText = null;
      _expandedKey = null;
    });
    await Future.wait([_loadHistory(), _loadSummary()]);
    if (!mounted) return;
    setState(() => _loading = false);
  }

  Future<void> _loadHistory() async {
    try {
      final histRes = await _api.getRaw(
        '/memory/history',
        queryParams: {
          'group': 'daily',
          'limit': '31',
          'offset': '0',
        },
      );
      HistoryResponse? hist;
      if (histRes.ok && histRes.data != null) {
        final d = histRes.data!;
        if (d.containsKey('items')) {
          hist = HistoryResponse.fromJson(d);
        } else if (d['data'] is Map) {
          hist = HistoryResponse.fromJson(
            Map<String, dynamic>.from(d['data'] as Map),
          );
        }
      }
      if (!mounted) return;
      setState(() {
        _history = hist;
        if (hist == null && histRes.errorMessage.isNotEmpty) {
          _error = histRes.errorMessage;
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  Future<void> _loadSummary() async {
    setState(() => _summaryLoading = true);
    try {
      final summaryType = _group.toUpperCase();
      final sumRes = await _api.getRaw(
        '/memory/period-summary',
        queryParams: {'summary_type': summaryType},
      );
      String? narrative;
      if (sumRes.ok && sumRes.data != null) {
        narrative = sumRes.data!['narrative_summary']?.toString();
      }
      if (!mounted) return;
      setState(() {
        _summaryText = narrative;
        _summaryLoading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _summaryLoading = false);
    }
  }

  String _todayKey() {
    final fromBackend = _history?.currentGroupKey;
    if (fromBackend != null && fromBackend.isNotEmpty) return fromBackend;
    final n = DateTime.now();
    final pad = (int v) => v.toString().padLeft(2, '0');
    return '${n.year}-${pad(n.month)}-${pad(n.day)}';
  }

  List<HistoryGroupItem> _archiveDays() {
    final today = _todayKey();
    return (_history?.items ?? const [])
        .where((g) => g.key != today)
        .toList(growable: false);
  }

  String _formatDayLabel(String key, LifestyleL10n l10n) {
    final formatted = CalendarDateMath.formatIsoForProfileDisplay(key, l10n.lang);
    final dt = CalendarDateMath.parseIsoLocalDate(key);
    if (dt == null) return formatted;
    final weekday = l10n.weekdayShort(dt.weekday);
    if (weekday.isEmpty) return formatted;
    final sep = l10n.lang == 'en' ? ', ' : '، ';
    return '$weekday$sep$formatted';
  }

  @override
  Widget build(BuildContext context) {
    final l10n = _l10n;
    return Directionality(
      textDirection: l10n.isRtl ? TextDirection.rtl : TextDirection.ltr,
      child: Scaffold(
        backgroundColor: A3DestinationSurface.canvas,
        appBar: A3PageAppBar(
          title: Text(l10n.myHistory),
          backgroundColor: A3DestinationSurface.canvas,
        ),
        body: RefreshIndicator(
          color: AppTheme.gate2ButtonOlive,
          onRefresh: _load,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
            children: [
              A3DestinationCard(
                child: Text(
                  l10n.historyExplain,
                  style: const TextStyle(
                    color: AppTheme.textSecondary,
                    height: 1.4,
                    fontSize: 14,
                  ),
                ),
              ),
              const SizedBox(height: 16),
              A3DestinationCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      l10n.sediSummaries,
                      style: const TextStyle(
                        fontWeight: FontWeight.w600,
                        color: AppTheme.textSecondary,
                        fontSize: 14,
                      ),
                    ),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        _chip('daily', l10n.daily),
                        _chip('weekly', l10n.weekly),
                        _chip('monthly', l10n.monthly),
                        _chip('yearly', l10n.yearly),
                      ],
                    ),
                    const SizedBox(height: 12),
                    if (_loading || _summaryLoading)
                      const Center(
                        child: Padding(
                          padding: EdgeInsets.symmetric(vertical: 12),
                          child: CircularProgressIndicator(
                            color: AppTheme.gate2ButtonOlive,
                          ),
                        ),
                      )
                    else
                      Text(
                        (_summaryText != null && _summaryText!.trim().isNotEmpty)
                            ? _summaryText!
                            : l10n.noSummary,
                        style: const TextStyle(
                          color: AppTheme.textPrimary,
                          height: 1.4,
                          fontSize: 14,
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 20),
              Text(
                l10n.conversationsLast30Days,
                style: const TextStyle(
                  fontWeight: FontWeight.w700,
                  color: AppTheme.textPrimary,
                  fontSize: 16,
                ),
              ),
              const SizedBox(height: 10),
              if (!_loading) ..._conversationCards(l10n),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _conversationCards(LifestyleL10n l10n) {
    if (_error != null && _history == null) {
      return [
        Text(
          _error!,
          style: const TextStyle(color: AppTheme.dangerRed, fontSize: 13),
        ),
      ];
    }

    final days = _archiveDays();
    if (days.isEmpty) {
      return [
        Text(
          l10n.noConversations,
          style: const TextStyle(
            color: AppTheme.textSecondary,
            fontSize: 13,
            height: 1.35,
          ),
        ),
      ];
    }

    return [
      for (final group in days)
        Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: _DayArchiveCard(
            group: group,
            expanded: _expandedKey == group.key,
            dateLabel: _formatDayLabel(group.key, l10n),
            countLabel: CalendarDateMath.localizeDigitsForLanguage(
              l10n.turnCount(group.turns.length),
              l10n.lang,
            ),
            onToggle: () {
              setState(() {
                _expandedKey = _expandedKey == group.key ? null : group.key;
              });
            },
          ),
        ),
    ];
  }

  Widget _chip(String key, String label) {
    return A3DestinationChip(
      label: label,
      selected: _group == key,
      onTap: () {
        if (_group == key) return;
        setState(() => _group = key);
        _loadSummary();
      },
    );
  }
}

class _DayArchiveCard extends StatelessWidget {
  final HistoryGroupItem group;
  final bool expanded;
  final String dateLabel;
  final String countLabel;
  final VoidCallback onToggle;

  const _DayArchiveCard({
    required this.group,
    required this.expanded,
    required this.dateLabel,
    required this.countLabel,
    required this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    return A3DestinationCard(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      borderColor: expanded ? AppTheme.gate2ButtonOlive.withOpacity(0.45) : null,
      onTap: onToggle,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      dateLabel,
                      style: const TextStyle(
                        color: AppTheme.textPrimary,
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      countLabel,
                      style: const TextStyle(
                        color: AppTheme.textSecondary,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              Icon(
                expanded
                    ? Icons.keyboard_arrow_up_rounded
                    : Icons.keyboard_arrow_down_rounded,
                size: 20,
                color: expanded
                    ? AppTheme.gate2ButtonOlive
                    : AppTheme.textSecondary,
              ),
            ],
          ),
          ClipRect(
            child: AnimatedSize(
              duration: const Duration(milliseconds: 220),
              curve: Curves.easeInOut,
              alignment: Alignment.topCenter,
              child: expanded
                  ? Padding(
                      padding: const EdgeInsets.only(top: 12),
                      child: _ReadOnlyTranscript(turns: group.turns),
                    )
                  : const SizedBox(width: double.infinity, height: 0),
            ),
          ),
        ],
      ),
    );
  }
}

class _ReadOnlyTranscript extends StatelessWidget {
  final List<HistoryTurnItem> turns;

  const _ReadOnlyTranscript({
    required this.turns,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (var i = 0; i < turns.length; i++) ...[
          if (i > 0) const SizedBox(height: 14),
          _HistoryUserBubble(text: turns[i].userMessage),
          if ((turns[i].sediResponse ?? '').trim().isNotEmpty) ...[
            const SizedBox(height: 8),
            _HistorySediText(text: turns[i].sediResponse!.trim()),
          ],
        ],
      ],
    );
  }
}

class _HistoryUserBubble extends StatelessWidget {
  final String text;

  const _HistoryUserBubble({required this.text});

  @override
  Widget build(BuildContext context) {
    final body = text.trim();
    if (body.isEmpty) return const SizedBox.shrink();
    return Align(
      alignment: AlignmentDirectional.centerEnd,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 300),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: AppTheme.metalGrey.withOpacity(0.15),
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(AppTheme.radiusLarge),
              topRight: Radius.circular(AppTheme.radiusLarge),
              bottomLeft: Radius.circular(AppTheme.radiusLarge),
              bottomRight: Radius.circular(AppTheme.radiusSmall),
            ),
            border: Border.all(
              color: AppTheme.metalGrey.withOpacity(0.35),
              width: 1,
            ),
            boxShadow: AppTheme.softShadow,
          ),
          child: Text(
            body,
            textAlign: TextAlign.start,
            style: const TextStyle(
              color: AppTheme.textPrimary,
              fontSize: 15,
              height: 1.45,
            ),
          ),
        ),
      ),
    );
  }
}

class _HistorySediText extends StatelessWidget {
  final String text;

  const _HistorySediText({required this.text});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: AlignmentDirectional.centerStart,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 320),
        child: Text(
          text,
          textAlign: TextAlign.start,
          style: const TextStyle(
            color: AppTheme.textPrimary,
            fontSize: 15,
            height: 1.45,
          ),
        ),
      ),
    );
  }
}
