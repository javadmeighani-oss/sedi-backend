import 'package:flutter/material.dart';

import '../../../../core/locale/sedi_locale_controller.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../services/lifestyle/lifestyle_health_service.dart';
import '../../../gate3_interactive/presentation/widgets/a3_destination_surface.dart';
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

  String _formatTs(String? raw) =>
      A3DestinationSurface.formatIsoTimestamp(raw, _l10n.lang);

  @override
  Widget build(BuildContext context) {
    final l10n = _l10n;
    return Directionality(
      textDirection: l10n.isRtl ? TextDirection.rtl : TextDirection.ltr,
      child: Scaffold(
        backgroundColor: A3DestinationSurface.canvas,
        appBar: A3PageAppBar(
          title: Text(l10n.health),
          backgroundColor: A3DestinationSurface.canvas,
        ),
        body: RefreshIndicator(
          color: AppTheme.gate2ButtonOlive,
          onRefresh: _load,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
            children: [
              if (_loading)
                const Padding(
                  padding: EdgeInsets.only(top: 40),
                  child: Center(
                    child: CircularProgressIndicator(
                      color: AppTheme.gate2ButtonOlive,
                    ),
                  ),
                )
              else if (_error != null)
                A3DestinationCard(
                  child: Text(
                    _error!,
                    style: const TextStyle(color: AppTheme.dangerRed),
                  ),
                )
              else ...[
                _latestHrCard(l10n),
                if (_data?.isDeviceReportedStatus == true) ...[
                  const SizedBox(height: 16),
                  _statusBlock(l10n),
                ],
                const SizedBox(height: 16),
                _rangeCard(l10n),
                const SizedBox(height: 16),
                _historyCard(l10n),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _latestHrCard(LifestyleL10n l10n) {
    final value = _data?.latestValue;
    return A3DestinationCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            l10n.latestHr,
            style: const TextStyle(
              color: AppTheme.textSecondary,
              fontSize: 13,
              fontWeight: FontWeight.w500,
            ),
          ),
          const SizedBox(height: 8),
          if (value != null)
            Text.rich(
              TextSpan(
                children: [
                  TextSpan(
                    text: '${value.round()}',
                    style: const TextStyle(
                      fontSize: 40,
                      fontWeight: FontWeight.w700,
                      height: 1.05,
                      color: AppTheme.textPrimary,
                    ),
                  ),
                  const TextSpan(
                    text: '  bpm',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w500,
                      color: AppTheme.textSecondary,
                    ),
                  ),
                ],
              ),
            )
          else
            Text(
              l10n.noHrData,
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w600,
                color: AppTheme.textPrimary,
              ),
            ),
          const SizedBox(height: 12),
          Text(
            l10n.lastReceived,
            style: const TextStyle(
              color: AppTheme.textSecondary,
              fontSize: 12,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            _formatTs(_data?.latestReceivedAt),
            style: const TextStyle(
              color: AppTheme.textSecondary,
              fontSize: 14,
            ),
          ),
        ],
      ),
    );
  }

  Widget _statusBlock(LifestyleL10n l10n) {
    // Caller must already gate with isDeviceReportedStatus (STABLE|UNSTABLE only).
    final code = (_data?.hrStatus ?? '').trim().toUpperCase();
    final color = _statusColor(code);
    return A3DestinationCard(
      borderColor: color.withOpacity(0.45),
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

  Widget _rangeCard(LifestyleL10n l10n) {
    return A3DestinationCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            l10n.historyRange,
            style: const TextStyle(
              fontWeight: FontWeight.w600,
              color: AppTheme.textPrimary,
              fontSize: 15,
            ),
          ),
          const SizedBox(height: 12),
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
        ],
      ),
    );
  }

  Widget _historyCard(LifestyleL10n l10n) {
    final history = _data?.history ?? const [];
    return A3DestinationCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_data?.availableFrom != null || _data?.availableTo != null) ...[
            if (_data?.availableFrom != null)
              Text(
                '${l10n.availableFrom}: ${_formatTs(_data?.availableFrom)}',
                style: const TextStyle(
                  color: AppTheme.textSecondary,
                  fontSize: 12,
                ),
              ),
            if (_data?.availableTo != null)
              Text(
                '${l10n.availableTo}: ${_formatTs(_data?.availableTo)}',
                style: const TextStyle(
                  color: AppTheme.textSecondary,
                  fontSize: 12,
                ),
              ),
            const SizedBox(height: 12),
          ],
          if (history.isEmpty)
            Text(
              l10n.noHrData,
              style: const TextStyle(color: AppTheme.textSecondary),
            )
          else
            ...history.map((p) {
              return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        _formatTs(p['bucket_start']?.toString()),
                        style: const TextStyle(
                          color: AppTheme.textSecondary,
                          fontSize: 13,
                        ),
                      ),
                    ),
                    Text(
                      p['avg'] != null
                          ? '${(p['avg'] as num).round()} bpm'
                          : '—',
                      style: const TextStyle(
                        fontWeight: FontWeight.w600,
                        color: AppTheme.textPrimary,
                      ),
                    ),
                  ],
                ),
              );
            }),
        ],
      ),
    );
  }

  Widget _rangeChip(String key, String label) {
    return A3DestinationChip(
      label: label,
      selected: _range == key,
      onTap: () {
        if (_range == key) return;
        setState(() => _range = key);
        _load();
      },
    );
  }
}
