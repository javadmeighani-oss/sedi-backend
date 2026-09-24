import 'package:flutter/material.dart';

import '../../../../core/locale/sedi_locale_controller.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../services/lifestyle/lifestyle_schedule_service.dart';
import '../../../gate3_interactive/presentation/widgets/a3_destination_surface.dart';
import '../../../gate3_interactive/presentation/widgets/a3_page_app_bar.dart';
import '../lifestyle_l10n.dart';

class LifestyleSchedulePage extends StatefulWidget {
  const LifestyleSchedulePage({super.key});

  @override
  State<LifestyleSchedulePage> createState() => _LifestyleSchedulePageState();
}

class _LifestyleSchedulePageState extends State<LifestyleSchedulePage> {
  final _svc = LifestyleScheduleService();
  List<LifestyleUserEventDto> _events = const [];
  List<LifestyleI8ActionDto> _actions = const [];
  bool _loading = true;
  String? _error;

  LifestyleL10n get _l10n =>
      LifestyleL10n(SediLocaleController.instance.languageCode);

  static const _presets = <int?>[null, 0, 15, 30, 60, 1440];

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
    final ev = await _svc.listEvents();
    final ac = await _svc.listI8Actions();
    if (!mounted) return;
    setState(() {
      _loading = false;
      _events = ev.data ?? const [];
      _actions = ac.data ?? const [];
      if (!ev.ok) _error = ev.errorMessage;
    });
  }

  DateTime? _parse(String? s) => s == null ? null : DateTime.tryParse(s)?.toLocal();

  String _bucketFor(DateTime dt) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final d = DateTime(dt.year, dt.month, dt.day);
    if (d == today) return 'today';
    if (d == today.add(const Duration(days: 1))) return 'tomorrow';
    if (d.isAfter(today) && d.isBefore(today.add(const Duration(days: 7)))) {
      return 'week';
    }
    return 'later';
  }

  Future<void> _setReminder(LifestyleUserEventDto e, int? minutes) async {
    final enabled = minutes != null;
    final offsets = minutes == null ? <int>[] : <int>[minutes];
    final res = await _svc.patchReminder(
      eventId: e.id,
      enabled: enabled,
      offsets: offsets,
    );
    if (!mounted) return;
    if (res.ok) {
      await _load();
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(res.errorMessage)),
      );
    }
  }

  String _presetLabel(LifestyleL10n l10n, int? m) {
    switch (m) {
      case null:
        return l10n.reminderOff;
      case 0:
        return l10n.reminderAtTime;
      case 15:
        return l10n.reminder15;
      case 30:
        return l10n.reminder30;
      case 60:
        return l10n.reminder1h;
      case 1440:
        return l10n.reminder1d;
      default:
        return l10n.reminderOff;
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = _l10n;
    final grouped = <String, List<LifestyleUserEventDto>>{
      'today': [],
      'tomorrow': [],
      'week': [],
      'later': [],
    };
    for (final e in _events) {
      final dt = _parse(e.startsAt);
      if (dt == null) {
        grouped['later']!.add(e);
      } else {
        grouped[_bucketFor(dt)]!.add(e);
      }
    }

    return Directionality(
      textDirection: l10n.isRtl ? TextDirection.rtl : TextDirection.ltr,
      child: Scaffold(
        backgroundColor: A3DestinationSurface.canvas,
        appBar: A3PageAppBar(
          title: Text(l10n.mySchedule),
          backgroundColor: A3DestinationSurface.canvas,
        ),
        body: RefreshIndicator(
          color: AppTheme.gate2ButtonOlive,
          onRefresh: _load,
          child: _loading
              ? ListView(children: const [
                  SizedBox(height: 80),
                  Center(
                    child: CircularProgressIndicator(
                      color: AppTheme.gate2ButtonOlive,
                    ),
                  ),
                ])
              : ListView(
                  padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
                  children: [
                    if (_error != null)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 16),
                        child: A3DestinationCard(
                          child: Text(
                            _error!,
                            style: const TextStyle(color: AppTheme.dangerRed),
                          ),
                        ),
                      ),
                    _section(l10n.today, grouped['today']!, l10n),
                    _section(l10n.tomorrow, grouped['tomorrow']!, l10n),
                    _section(l10n.thisWeek, grouped['week']!, l10n),
                    _section(l10n.later, grouped['later']!, l10n),
                    const SizedBox(height: 8),
                    Text(
                      l10n.governedActions,
                      style: const TextStyle(
                        fontWeight: FontWeight.w700,
                        color: AppTheme.textPrimary,
                        fontSize: 16,
                      ),
                    ),
                    const SizedBox(height: 12),
                    if (_actions.isEmpty)
                      A3DestinationCard(
                        child: Text(
                          l10n.noEvents,
                          style: const TextStyle(color: AppTheme.textSecondary),
                        ),
                      )
                    else
                      ..._actions.map(
                        (a) => Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: A3DestinationCard(
                            padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
                            child: Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    a.title,
                                    style: const TextStyle(
                                      color: AppTheme.textPrimary,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Text(
                                  l10n.scheduleStatusLabel(a.status),
                                  style: const TextStyle(
                                    color: AppTheme.textSecondary,
                                    fontSize: 13,
                                  ),
                                ),
                              ],
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

  Widget _section(
      String title, List<LifestyleUserEventDto> items, LifestyleL10n l10n) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontWeight: FontWeight.w700,
              color: AppTheme.textPrimary,
              fontSize: 16,
            ),
          ),
          const SizedBox(height: 12),
          if (items.isEmpty)
            A3DestinationCard(
              child: Text(
                l10n.noEvents,
                style: const TextStyle(color: AppTheme.textSecondary),
              ),
            )
          else
            ...items.map((e) => _eventTile(e, l10n)),
        ],
      ),
    );
  }

  Widget _eventTile(LifestyleUserEventDto e, LifestyleL10n l10n) {
    final current = !e.reminderEnabled
        ? null
        : (e.reminderOffsets.isEmpty ? 0 : e.reminderOffsets.first);
    final when = A3DestinationSurface.formatIsoTimestamp(e.startsAt, l10n.lang);
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: A3DestinationCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              e.title,
              style: const TextStyle(
                fontWeight: FontWeight.w600,
                fontSize: 16,
                color: AppTheme.textPrimary,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              when,
              style: const TextStyle(
                color: AppTheme.textSecondary,
                fontSize: 13,
              ),
            ),
            if (e.location != null && e.location!.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(
                e.location!,
                style: const TextStyle(
                  color: AppTheme.textSecondary,
                  fontSize: 13,
                ),
              ),
            ],
            if (e.eventType != null && e.eventType!.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(
                e.eventType!,
                style: const TextStyle(
                  color: AppTheme.textSecondary,
                  fontSize: 13,
                ),
              ),
            ],
            const SizedBox(height: 6),
            Text(
              l10n.scheduleStatusLabel(e.status),
              style: const TextStyle(
                color: AppTheme.textSecondary,
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 12),
            Text(
              l10n.reminder,
              style: const TextStyle(
                color: AppTheme.textSecondary,
                fontSize: 12,
              ),
            ),
            DropdownButton<int?>(
              value: _presets.contains(current) ? current : null,
              isExpanded: true,
              underline: const SizedBox.shrink(),
              items: _presets
                  .map((m) => DropdownMenuItem(
                        value: m,
                        child: Text(_presetLabel(l10n, m)),
                      ))
                  .toList(),
              onChanged: (v) => _setReminder(e, v),
            ),
          ],
        ),
      ),
    );
  }
}
