import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../../../../core/theme/app_theme.dart';
import '../../../../../core/widgets/app_states/app_empty_state.dart';
import '../../../../../core/widgets/app_states/app_error_state.dart';
import '../../../../../core/widgets/app_states/app_loading_state.dart';
import '../../../logic/health_care_section_controller.dart';
import '../../../../../data/dto/gate3/user_medication_dto.dart';
import '../../../../../data/dto/gate3/vitals_summary_dto.dart';
import '../../gate3_sections_localization.dart';
import '../../widgets/gate3_section_card.dart';
import '../../widgets/gate3_section_scaffold.dart';

class Gate3HealthCarePage extends StatefulWidget {
  final String lang;

  const Gate3HealthCarePage({super.key, required this.lang});

  @override
  State<Gate3HealthCarePage> createState() => _Gate3HealthCarePageState();
}

class _Gate3HealthCarePageState extends State<Gate3HealthCarePage> {
  late final HealthCareSectionController _controller;

  @override
  void initState() {
    super.initState();
    _controller = HealthCareSectionController(lang: widget.lang);
    _controller.addListener(_onChanged);
    _controller.load();
  }

  @override
  void dispose() {
    _controller.removeListener(_onChanged);
    _controller.dispose();
    super.dispose();
  }

  void _onChanged() {
    if (mounted) setState(() {});
  }

  Gate3SectionsLocalization get l10n => Gate3SectionsLocalization(widget.lang);

  @override
  Widget build(BuildContext context) {
    return Gate3SectionScaffold(
      lang: widget.lang,
      title: l10n.healthCareTitle,
      isRefreshing: _controller.refreshing,
      onRefresh: () => _controller.load(isRefresh: true),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_controller.loading && _controller.vitals == null) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [AppLoadingState(label: l10n.loading)],
      );
    }

    if (_controller.error != null && _controller.vitals == null) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          AppErrorState(
            message: _controller.error!,
            onRetry: () => _controller.load(),
          ),
        ],
      );
    }

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      children: [
        if (_controller.actionMessage != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(
              _controller.actionMessage!,
              style: const TextStyle(color: AppTheme.gate2ButtonOlive),
            ),
          ),
        if (_controller.lastLoadedAt != null)
          Text(
            '${l10n.lastUpdated}: ${DateFormat.yMMMd().add_Hm().format(_controller.lastLoadedAt!)}',
            style: const TextStyle(fontSize: 12, color: AppTheme.textSecondary),
          ),
        const SizedBox(height: 8),
        _vitalsSection(),
        _medicationsSection(),
        _appointmentsSection(),
        _careSection(),
      ],
    );
  }

  Widget _vitalsSection() {
    final v = _controller.vitals;
    final rows = <Widget>[];

    if (v?.monitoringState != null) {
      rows.add(Text(
        '${l10n.monitoringStateLabel(v!.monitoringState!)}',
        style: const TextStyle(fontWeight: FontWeight.w600),
      ));
      rows.add(const SizedBox(height: 8));
    }

    void addFromDto(String label, VitalReadingDto? dto, {String? fallbackUnit}) {
      if (dto == null || dto.displayValue == null) return;
      final unit = dto.unit ?? fallbackUnit;
      final at = dto.receivedAt ?? dto.recordedAt;
      rows.add(_vitalRow(
        label,
        '${dto.displayValue}${unit != null ? ' $unit' : ''}',
        at,
        freshness: dto.freshness,
        source: dto.source,
      ));
    }

    if (v != null && v.vitals.isNotEmpty) {
      addFromDto(l10n.heartRate, v.vitals['heart_rate'], fallbackUnit: 'bpm');
      addFromDto(l10n.spo2, v.vitals['spo2'], fallbackUnit: '%');
      addFromDto(l10n.temperature, v.vitals['temperature'], fallbackUnit: '°C');
      addFromDto(l10n.bloodPressure, v.vitals['blood_pressure']);
      addFromDto(l10n.respiratoryRate, v.vitals['respiratory_rate'], fallbackUnit: '/min');
      final ecg = v.vitals['ecg'];
      if (ecg?.signalAvailable == true) {
        rows.add(Text(
          'ECG: ${l10n.hubStatusLabel('connected')}',
          style: const TextStyle(fontSize: 12, color: AppTheme.textSecondary),
        ));
      }
    } else {
      final lh = v?.legacyHealth;
      final de = v?.deviceEvent;
      if (lh != null) {
        if (lh['heart_rate'] != null) {
          rows.add(_vitalRow(l10n.heartRate, '${lh['heart_rate']} bpm', lh['recorded_at']?.toString()));
        }
        if (lh['spo2'] != null) {
          rows.add(_vitalRow(l10n.spo2, '${lh['spo2']} %', lh['recorded_at']?.toString()));
        }
        if (lh['temperature'] != null) {
          rows.add(_vitalRow(l10n.temperature, '${lh['temperature']} °C', lh['recorded_at']?.toString()));
        }
      }
      if (de != null) {
        final payload = de['payload'];
        if (payload is Map) {
          if (payload['heart_rate'] != null) {
            rows.add(_vitalRow(l10n.heartRate, '${payload['heart_rate']} bpm', de['received_at']?.toString()));
          }
        }
        rows.add(Text(
          '${l10n.sourceLabel}: ${de['event_type'] ?? l10n.gadgetConnectionNotConfirmed}',
          style: const TextStyle(fontSize: 12, color: AppTheme.textSecondary),
        ));
      }
    }

    if (rows.isEmpty) {
      rows.add(Text(l10n.noRecentData, style: const TextStyle(color: AppTheme.textSecondary)));
    }

    return Gate3SectionCard(title: l10n.vitalSigns, child: Column(children: rows));
  }

  Widget _vitalRow(String label, String value, String? at, {String? freshness, String? source}) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: Text(label, style: const TextStyle(fontWeight: FontWeight.w600))),
              Text(value),
              if (at != null && at.isNotEmpty) ...[
                const SizedBox(width: 8),
                Flexible(
                  child: Text(
                    _formatAt(at),
                    style: const TextStyle(fontSize: 11, color: AppTheme.textSecondary),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ],
          ),
          if (freshness == 'stale')
            Text(l10n.staleData, style: const TextStyle(fontSize: 11, color: AppTheme.textSecondary)),
          if (source != null && source.isNotEmpty)
            Text('${l10n.sourceLabel}: $source',
                style: const TextStyle(fontSize: 11, color: AppTheme.textSecondary)),
        ],
      ),
    );
  }

  String _formatAt(String raw) {
    final dt = DateTime.tryParse(raw);
    if (dt == null) return l10n.lastUpdateUnavailable;
    return DateFormat.MMMd().add_Hm().format(dt.toLocal());
  }

  Widget _medicationsSection() {
    final meds = _controller.medications;
    if (meds.isEmpty) {
      return Gate3SectionCard(
        title: l10n.medications,
        child: AppEmptyState(title: l10n.noMedications),
      );
    }
    return Gate3SectionCard(
      title: l10n.medications,
      child: Column(
        children: meds.map((m) {
          final subtitle = [
            if (m.userDosage != null) m.userDosage!,
            if (m.instructions != null) m.instructions!,
            if (m.reminderTimes.isNotEmpty) m.reminderTimes.join(', '),
            if (m.stockLevel != null && m.stockLevel != 'unknown')
              '${l10n.stockLevelLabel}: ${m.stockLevel}',
          ].where((s) => s.isNotEmpty).join(' · ');
          return ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(m.name),
            subtitle: subtitle.isNotEmpty ? Text(subtitle) : null,
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  m.reminderEnabled
                      ? Icons.notifications_active_outlined
                      : Icons.notifications_off_outlined,
                  size: 18,
                  color: m.reminderEnabled
                      ? AppTheme.gate2ButtonOlive
                      : AppTheme.textSecondary.withOpacity(0.5),
                ),
                IconButton(
                  icon: const Icon(Icons.schedule_outlined, size: 18),
                  tooltip: l10n.editSchedule,
                  onPressed: () => _openMedicationSchedule(m),
                ),
              ],
            ),
          );
        }).toList(),
      ),
    );
  }

  Future<void> _openMedicationSchedule(UserMedicationDto med) async {
    final timesCtrl = TextEditingController(text: med.reminderTimes.join(', '));
    final intervalCtrl = TextEditingController(text: '${med.intervalHours}');
    final tzCtrl = TextEditingController(text: med.timezone ?? 'Asia/Tehran');
    var reminderOn = med.reminderEnabled;

    final saved = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppTheme.gate3PaleOliveBackground,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setLocal) {
            return Padding(
              padding: EdgeInsets.only(
                left: 20,
                right: 20,
                top: 16,
                bottom: MediaQuery.of(ctx).viewInsets.bottom + 20,
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(med.name, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(l10n.reminderEnabledLabel),
                    value: reminderOn,
                    onChanged: (v) => setLocal(() => reminderOn = v),
                  ),
                  TextField(
                    controller: timesCtrl,
                    decoration: InputDecoration(labelText: l10n.reminderTimesLabel),
                  ),
                  TextField(
                    controller: intervalCtrl,
                    keyboardType: TextInputType.number,
                    decoration: InputDecoration(labelText: l10n.intervalHoursLabel),
                  ),
                  TextField(
                    controller: tzCtrl,
                    decoration: InputDecoration(labelText: l10n.timezoneLabel),
                  ),
                  const SizedBox(height: 12),
                  FilledButton(
                    onPressed: () => Navigator.pop(ctx, true),
                    child: Text(l10n.save),
                  ),
                ],
              ),
            );
          },
        );
      },
    );

    if (saved != true) return;
    final times = timesCtrl.text
        .split(',')
        .map((s) => s.trim())
        .where((s) => s.isNotEmpty)
        .toList();
    final interval = int.tryParse(intervalCtrl.text.trim());
    await _controller.updateMedicationSchedule(
      med,
      reminderEnabled: reminderOn,
      reminderTimes: times.isEmpty ? null : times,
      intervalHours: interval,
      timezone: tzCtrl.text.trim().isEmpty ? null : tzCtrl.text.trim(),
    );
  }

  Widget _appointmentsSection() {
    final items = _controller.medicalEvents;
    if (items.isEmpty) {
      return Gate3SectionCard(
        title: l10n.appointments,
        child: Column(
          children: [
            AppEmptyState(title: l10n.noAppointments),
            Text(l10n.reminderPlanned,
                style: const TextStyle(fontSize: 12, color: AppTheme.textSecondary)),
          ],
        ),
      );
    }
    return Gate3SectionCard(
      title: l10n.appointments,
      child: Column(
        children: items.map((e) {
          return ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(e['title']?.toString() ?? ''),
            subtitle: Text([
              e['starts_at']?.toString() ?? '',
              if (e['event_type'] != null) e['event_type'].toString(),
              if (e['reminder_enabled'] == true) l10n.reminderEnabledLabel,
            ].where((s) => s.isNotEmpty).join(' · ')),
          );
        }).toList(),
      ),
    );
  }

  Widget _careSection() {
    final recs = _controller.recommendations;
    final follow = _controller.followUps;
    if (recs.isEmpty && follow.isEmpty && _controller.carePlanNotes.isEmpty) {
      return Gate3SectionCard(
        title: l10n.careInfo,
        child: AppEmptyState(title: l10n.noCareItems),
      );
    }
    return Gate3SectionCard(
      title: l10n.careInfo,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ...recs.take(5).map((r) => Text('• ${r['title'] ?? r['body'] ?? ''}')),
          ...follow.take(5).map((f) => Text('• ${f['title'] ?? ''}')),
          ..._controller.carePlanNotes.map((n) => Text('• $n')),
        ],
      ),
    );
  }
}
