import 'package:flutter/material.dart';

import '../../../../core/locale/sedi_locale_controller.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../services/lifestyle/lifestyle_health_service.dart';
import '../../../gate3_interactive/presentation/widgets/a3_page_app_bar.dart';
import '../lifestyle_l10n.dart';

class LifestyleHealthPage extends StatefulWidget {
  const LifestyleHealthPage({super.key});

  @override
  State<LifestyleHealthPage> createState() => _LifestyleHealthPageState();
}

class _LifestyleHealthPageState extends State<LifestyleHealthPage> {
  final _svc = LifestyleHealthService();
  String _range = '7d';
  LifestyleHealthHrDto? _data;
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
    final res = await _svc.fetchHr(rangeKey: _range);
    if (!mounted) return;
    setState(() {
      _loading = false;
      if (res.ok && res.data != null) {
        _data = res.data;
      } else {
        _error = res.errorMessage;
        _data = null;
      }
    });
  }

  Color _statusColor(String code) {
    switch (code.toUpperCase()) {
      case 'STABLE':
        return AppTheme.statusStableOlive;
      case 'UNSTABLE':
        return AppTheme.statusChangeAmber;
      default:
        return AppTheme.statusNeutralMuted;
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
          title: Text(l10n.health),
        ),
        body: RefreshIndicator(
          onRefresh: _load,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
            children: [
              if (_loading)
                const Padding(
                  padding: EdgeInsets.only(top: 40),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (_error != null)
                Text(_error!, style: const TextStyle(color: AppTheme.dangerRed))
              else ...[
                if (_data?.isDeviceReportedStatus == true) ...[
                  _statusBlock(l10n),
                  const SizedBox(height: 20),
                ],
                Text(l10n.latestHr,
                    style: const TextStyle(color: AppTheme.textSecondary)),
                Text(
                  _data?.latestValue != null
                      ? '${_data!.latestValue!.round()} bpm'
                      : l10n.noHrData,
                  style: const TextStyle(
                      fontSize: 28,
                      fontWeight: FontWeight.w700,
                      color: AppTheme.textPrimary),
                ),
                const SizedBox(height: 8),
                Text(l10n.lastReceived,
                    style: const TextStyle(color: AppTheme.textSecondary)),
                Text(_data?.latestReceivedAt ?? '—',
                    style: const TextStyle(color: AppTheme.textPrimary)),
                const SizedBox(height: 20),
                Text(l10n.historyRange,
                    style: const TextStyle(
                        fontWeight: FontWeight.w600, color: AppTheme.textPrimary)),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    _rangeChip('7d', l10n.range7d),
                    _rangeChip('30d', l10n.range30d),
                    _rangeChip('3m', l10n.range3m),
                    _rangeChip('1y', l10n.range1y),
                  ],
                ),
                const SizedBox(height: 16),
                Text('${l10n.availableFrom}: ${_data?.availableFrom ?? '—'}',
                    style: const TextStyle(color: AppTheme.textSecondary)),
                Text('${l10n.availableTo}: ${_data?.availableTo ?? '—'}',
                    style: const TextStyle(color: AppTheme.textSecondary)),
                const SizedBox(height: 16),
                if ((_data?.history ?? []).isEmpty)
                  Text(l10n.noHrData,
                      style: const TextStyle(color: AppTheme.textSecondary))
                else
                  ...(_data!.history.map((p) => Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: Row(
                          children: [
                            Expanded(
                              child: Text(
                                '${p['bucket_start'] ?? '—'}',
                                style: const TextStyle(
                                    color: AppTheme.textSecondary, fontSize: 13),
                              ),
                            ),
                            Text(
                              p['avg'] != null
                                  ? '${(p['avg'] as num).round()} bpm'
                                  : '—',
                              style: const TextStyle(
                                  fontWeight: FontWeight.w600,
                                  color: AppTheme.textPrimary),
                            ),
                          ],
                        ),
                      ))),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _statusBlock(LifestyleL10n l10n) {
    // Caller must already gate with isDeviceReportedStatus (STABLE|UNSTABLE only).
    final code = (_data?.hrStatus ?? '').trim().toUpperCase();
    final color = _statusColor(code);
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.gate2CardWhite,
        borderRadius: BorderRadius.circular(AppTheme.radiusLarge),
        border: Border.all(color: color.withOpacity(0.45)),
      ),
      child: Row(
        children: [
          Icon(Icons.monitor_heart_outlined, color: color),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              l10n.deviceReportedHrStatusLabel(code),
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
                color: color,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _rangeChip(String key, String label) {
    final selected = _range == key;
    return ChoiceChip(
      label: Text(label),
      selected: selected,
      selectedColor: AppTheme.gate2ButtonOlive.withOpacity(0.2),
      labelStyle: TextStyle(
        color: selected ? AppTheme.gate2ButtonOlive : AppTheme.textSecondary,
      ),
      onSelected: (_) {
        if (_range == key) return;
        setState(() => _range = key);
        _load();
      },
    );
  }
}
