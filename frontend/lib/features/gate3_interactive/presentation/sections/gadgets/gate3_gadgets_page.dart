import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../../../../core/theme/app_theme.dart';
import '../../../../../core/widgets/app_states/app_empty_state.dart';
import '../../../../../core/widgets/app_states/app_error_state.dart';
import '../../../../../core/widgets/app_states/app_loading_state.dart';
import '../../../logic/gadgets_section_controller.dart';
import '../../gate3_sections_localization.dart';
import '../../widgets/gate3_section_card.dart';
import '../../widgets/gate3_section_scaffold.dart';

class Gate3GadgetsPage extends StatefulWidget {
  final String lang;

  const Gate3GadgetsPage({super.key, required this.lang});

  @override
  State<Gate3GadgetsPage> createState() => _Gate3GadgetsPageState();
}

class _Gate3GadgetsPageState extends State<Gate3GadgetsPage> {
  late final GadgetsSectionController _controller;

  @override
  void initState() {
    super.initState();
    _controller = GadgetsSectionController(lang: widget.lang);
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
      title: l10n.gadgetsTitle,
      isRefreshing: _controller.refreshing,
      onRefresh: () => _controller.load(isRefresh: true),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_controller.loading && _controller.hubStatus == null) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [AppLoadingState(label: l10n.loading)],
      );
    }

    if (_controller.error != null && _controller.hubStatus == null) {
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

    if (!_controller.hasHub) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(16),
        children: [
          AppEmptyState(
            title: l10n.noHubRegistered,
            subtitle: l10n.statusUnavailable,
          ),
        ],
      );
    }

    final hub = _controller.hub;
    final status = _controller.operationalStatus;

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      children: [
        if (_controller.lastLoadedAt != null)
          Text(
            '${l10n.lastUpdated}: ${DateFormat.yMMMd().add_Hm().format(_controller.lastLoadedAt!)}',
            style: const TextStyle(fontSize: 12, color: AppTheme.textSecondary),
          ),
        Gate3SectionCard(
          title: l10n.gadgetHubTitle,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _statusRow(l10n.hubStatus, l10n.hubStatusLabel(status)),
              if (hub != null) ...[
                if (hub['last_heartbeat_at'] != null)
                  _statusRow(l10n.lastUpdated, _formatAt(hub['last_heartbeat_at'].toString())),
                if (hub['last_sync_at'] != null)
                  _statusRow(l10n.syncLabel, _formatAt(hub['last_sync_at'].toString())),
                if (hub['battery_level'] != null)
                  _statusRow(l10n.batteryLabel, '${hub['battery_level']}%'),
              ],
            ],
          ),
        ),
        Gate3SectionCard(
          title: l10n.connectedSensors,
          child: _controller.sensors.isEmpty
              ? AppEmptyState(title: l10n.noSensors)
              : Column(
                  children: _controller.sensors.map((s) {
                    final conn = s['connection_status']?.toString() ?? 'unknown';
                    return ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(
                        s['display_name']?.toString() ??
                            s['sensor_type']?.toString() ??
                            '',
                      ),
                      subtitle: Text([
                        l10n.hubStatusLabel(conn),
                        if (s['last_signal_at'] != null)
                          '${l10n.lastSignalLabel}: ${_formatAt(s['last_signal_at'].toString())}',
                      ].join(' · ')),
                      trailing: s['battery_level'] != null
                          ? Text('${s['battery_level']}%')
                          : null,
                    );
                  }).toList(),
                ),
        ),
      ],
    );
  }

  Widget _statusRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        children: [
          Expanded(
            child: Text(label, style: const TextStyle(color: AppTheme.textSecondary)),
          ),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }

  String _formatAt(String raw) {
    final dt = DateTime.tryParse(raw);
    if (dt == null) return l10n.statusUnavailable;
    return DateFormat.MMMd().add_Hm().format(dt.toLocal());
  }
}
