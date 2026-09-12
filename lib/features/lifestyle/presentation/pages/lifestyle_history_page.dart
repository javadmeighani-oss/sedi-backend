import 'package:flutter/material.dart';

import '../../../../core/locale/sedi_locale_controller.dart';
import '../../../../core/network/api_client.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../data/dto/history_response.dart';
import '../../../gate3_interactive/presentation/widgets/a3_page_app_bar.dart';
import '../lifestyle_l10n.dart';
import 'lifestyle_page.dart';

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
  String? _error;

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
    });
    try {
      // JWT-only — do not send legacy user_id (BE rejects it).
      final histRes = await _api.getRaw(
        '/memory/history',
        queryParams: {
          'group': _group,
          'limit': '40',
          'offset': '0',
        },
      );
      // HistoryResponse may be envelope-wrapped or top-level.
      HistoryResponse? hist;
      if (histRes.ok && histRes.data != null) {
        final d = histRes.data!;
        if (d.containsKey('items')) {
          hist = HistoryResponse.fromJson(d);
        } else if (d['data'] is Map) {
          hist = HistoryResponse.fromJson(Map<String, dynamic>.from(d['data'] as Map));
        }
      }

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
        _history = hist;
        _summaryText = narrative;
        _loading = false;
        if (hist == null && histRes.errorMessage.isNotEmpty) {
          _error = histRes.errorMessage;
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = _l10n;
    return Directionality(
      textDirection: l10n.isRtl ? TextDirection.rtl : TextDirection.ltr,
      child: Scaffold(
        backgroundColor: AppTheme.gate3PaleOliveBackground,
        appBar: A3PageAppBar(
          title: Text(l10n.myHistory),
        ),
        body: RefreshIndicator(
          onRefresh: _load,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
            children: [
              Text(l10n.historyExplain,
                  style: const TextStyle(color: AppTheme.textSecondary, height: 1.4)),
              const SizedBox(height: 16),
              Text(l10n.sediSummaries,
                  style: const TextStyle(
                      fontWeight: FontWeight.w700, color: AppTheme.textPrimary)),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                children: [
                  _chip('daily', l10n.daily),
                  _chip('weekly', l10n.weekly),
                  _chip('monthly', l10n.monthly),
                  _chip('yearly', l10n.yearly),
                ],
              ),
              const SizedBox(height: 12),
              if (_loading)
                const Center(child: CircularProgressIndicator())
              else if (_error != null)
                Text(_error!, style: const TextStyle(color: AppTheme.dangerRed))
              else ...[
                Text(
                  (_summaryText != null && _summaryText!.trim().isNotEmpty)
                      ? _summaryText!
                      : l10n.noSummary,
                  style: const TextStyle(color: AppTheme.textPrimary, height: 1.35),
                ),
                const SizedBox(height: 24),
                Text(l10n.recentConversations,
                    style: const TextStyle(
                        fontWeight: FontWeight.w700, color: AppTheme.textPrimary)),
                const SizedBox(height: 8),
                ..._turnPreviews(l10n),
                const SizedBox(height: 16),
                TextButton(
                  onPressed: () => openLifestyleChat(context),
                  child: Text(l10n.openChat),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _turnPreviews(LifestyleL10n l10n) {
    final groups = _history?.items ?? const [];
    if (groups.isEmpty) {
      return [
        Text(l10n.noSummary, style: const TextStyle(color: AppTheme.textSecondary))
      ];
    }
    final out = <Widget>[];
    for (final g in groups.take(8)) {
      for (final t in g.turns.take(3)) {
        final preview = t.userMessage.trim();
        if (preview.isEmpty) continue;
        final short =
            preview.length > 80 ? '${preview.substring(0, 80)}…' : preview;
        out.add(Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: Text(short,
              style: const TextStyle(color: AppTheme.textPrimary, fontSize: 14)),
        ));
      }
    }
    if (out.isEmpty) {
      out.add(Text(l10n.noSummary,
          style: const TextStyle(color: AppTheme.textSecondary)));
    }
    return out;
  }

  Widget _chip(String key, String label) {
    final selected = _group == key;
    return ChoiceChip(
      label: Text(label),
      selected: selected,
      selectedColor: AppTheme.gate2ButtonOlive.withOpacity(0.2),
      onSelected: (_) {
        if (_group == key) return;
        setState(() => _group = key);
        _load();
      },
    );
  }
}
