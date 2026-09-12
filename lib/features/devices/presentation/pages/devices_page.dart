/// Devices screen: MVP ECG-only. Shows Sedi-connected ECG device or "Not connected" + Coming soon.
import 'package:flutter/material.dart';

import '../../../../core/health_subject/sedi_health_subject.dart';
import '../../../../core/health_subject/sedi_health_subject_controller.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../core/utils/user_preferences.dart';
import '../../../../data/dto/device_public_info.dart';
import '../../../gate3_interactive/presentation/widgets/a3_page_app_bar.dart';
import '../../logic/devices_controller.dart';

class DevicesPage extends StatefulWidget {
  const DevicesPage({super.key});

  @override
  State<DevicesPage> createState() => _DevicesPageState();
}

class _DevicesPageState extends State<DevicesPage> {
  final DevicesController _controller = DevicesController();
  bool _loading = true;
  String _language = 'en';

  @override
  void initState() {
    super.initState();
    _loadLanguage();
    _load();
  }

  Future<void> _loadLanguage() async {
    final lang = await UserPreferences.getUserLanguage();
    if (mounted) setState(() => _language = lang);
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    await _controller.loadDevices();
    if (mounted) setState(() => _loading = false);
  }

  bool get _isRtl => _language == 'fa' || _language == 'ar';

  static final _ecgTypes = {'ecg', 'heart_rate', 'heart-rate', 'hr'};
  static final _connectedStatuses = {'active', 'connected', 'online'};

  /// MVP: consider ECG-type device as first device with normalized type in [ecg, heart_rate, heart-rate, hr].
  /// Normalization: assumes deviceType/status are non-nullable from DTO; if ever nullable, use (value ?? '').toLowerCase().trim().
  DevicePublicInfo? get _ecgDevice {
    for (final d in _controller.devices) {
      final t = d.deviceType.toLowerCase().trim();
      if (_ecgTypes.contains(t)) return d;
    }
    return null;
  }

  bool get _ecgConnected {
    final d = _ecgDevice;
    if (d == null) return false;
    final s = d.status.toLowerCase().trim();
    return _connectedStatuses.contains(s);
  }

  String _lastSeenLabel(DateTime? lastSeenAt) {
    if (lastSeenAt == null) return 'Never';
    final n = DateTime.now();
    final d = lastSeenAt;
    if (d.year == n.year && d.month == n.month && d.day == n.day) {
      return '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
    }
    return '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final subjects = SediHealthSubjectController.instance.accessibleSubjects;
    final groups = _deviceGroups(subjects);

    Widget body = RefreshIndicator(
      onRefresh: _load,
      color: AppTheme.pistachioGreen,
      child: ListView(
        padding: const EdgeInsets.only(bottom: 24),
        children: [
          if (_loading)
            const Padding(
              padding: EdgeInsets.all(24),
              child: Center(
                  child:
                      CircularProgressIndicator(color: AppTheme.pistachioGreen)),
            )
          else ...[
            for (final g in groups) ...[
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
                child: Text(
                  g.title,
                  style: const TextStyle(
                    color: AppTheme.textSecondary,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              if (g.devices.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  child: Text('No devices',
                      style: TextStyle(color: AppTheme.textSecondary)),
                )
              else
                for (final d in g.devices) _deviceRow(d),
            ],
            const SizedBox(height: 8),
            _buildEcgCard(),
          ],
          const SizedBox(height: 16),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 16),
            child: Text(
              'When connected, ECG readings will appear in Vitals.',
              style: TextStyle(
                color: AppTheme.textSecondary,
                fontSize: 12,
              ),
            ),
          ),
        ],
      ),
    );

    Widget page = Scaffold(
      backgroundColor: AppTheme.backgroundWhite,
      appBar: const A3PageAppBar(
        title: Text('Devices'),
        backgroundColor: AppTheme.backgroundWhite,
        foregroundColor: AppTheme.primaryBlack,
      ),
      body: body,
    );

    if (_isRtl) {
      page = Directionality(
        textDirection: TextDirection.rtl,
        child: page,
      );
    }
    return page;
  }

  List<_DeviceGroup> _deviceGroups(List<SediHealthSubject> subjects) {
    final byId = <int?, List<DevicePublicInfo>>{};
    for (final d in _controller.devices) {
      byId.putIfAbsent(d.healthSubjectId, () => []).add(d);
    }
    final groups = <_DeviceGroup>[];
    // SELF first
    for (final s in subjects.where((s) => s.isSelf)) {
      groups.add(_DeviceGroup(
        title: 'My devices',
        healthSubjectId: s.id,
        devices: byId[s.id] ?? const [],
      ));
    }
    // OTHER by display_name
    for (final s in subjects.where((s) => !s.isSelf)) {
      groups.add(_DeviceGroup(
        title: s.visibleName,
        healthSubjectId: s.id,
        devices: byId[s.id] ?? const [],
      ));
    }
    // Unbound devices (no subject)
    final unbound = byId[null] ?? const [];
    if (unbound.isNotEmpty && groups.isEmpty) {
      groups.add(_DeviceGroup(
        title: 'My devices',
        healthSubjectId: null,
        devices: unbound,
      ));
    } else if (unbound.isNotEmpty) {
      groups.add(_DeviceGroup(
        title: 'Unassigned',
        healthSubjectId: null,
        devices: unbound,
      ));
    }
    if (groups.isEmpty) {
      groups.add(const _DeviceGroup(
        title: 'My devices',
        healthSubjectId: null,
        devices: [],
      ));
    }
    return groups;
  }

  Widget _deviceRow(DevicePublicInfo d) {
    return ListTile(
      title: Text(d.deviceType),
      subtitle: Text(deviceStatusLabel(d.status)),
      dense: true,
    );
  }

  Widget _buildEcgCard() {
    final connected = _ecgConnected;
    final d = _ecgDevice;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      decoration: BoxDecoration(
        color: AppTheme.backgroundWhite,
        border: Border.all(color: AppTheme.borderInactive.withOpacity(0.5)),
        borderRadius: BorderRadius.circular(AppTheme.radiusSmall),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 6),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'ECG Device',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                          color: AppTheme.textPrimary,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        'Chest device',
                        style: TextStyle(
                          fontSize: 13,
                          color: AppTheme.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: connected
                        ? AppTheme.pistachioGreen.withOpacity(0.2)
                        : AppTheme.borderInactive.withOpacity(0.3),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    connected ? 'Connected' : 'Not connected',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                      color: connected ? AppTheme.textPrimary : AppTheme.textSecondary,
                    ),
                  ),
                ),
              ],
            ),
          ),
          if (connected && d != null && d.lastSeenAt != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
              child: Text(
                'Last updated: ${_lastSeenLabel(d.lastSeenAt)}',
                style: TextStyle(color: AppTheme.textSecondary, fontSize: 12),
                textDirection: TextDirection.ltr,
              ),
            )
          else if (!connected) ...[
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
              child: Text(
                'Coming soon',
                style: TextStyle(color: AppTheme.textSecondary, fontSize: 12),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
              child: IgnorePointer(
                child: Opacity(
                  opacity: 0.6,
                  child: FilledButton(
                    onPressed: () {},
                    style: FilledButton.styleFrom(
                      backgroundColor: AppTheme.pistachioGreen,
                      foregroundColor: AppTheme.backgroundWhite,
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(AppTheme.radiusMedium),
                      ),
                    ),
                    child: const Text('Connect'),
                  ),
                ),
              ),
            ),
          ] else
            const SizedBox(height: 8),
        ],
      ),
    );
  }
}

class _DeviceGroup {
  final String title;
  final int? healthSubjectId;
  final List<DevicePublicInfo> devices;

  const _DeviceGroup({
    required this.title,
    required this.healthSubjectId,
    required this.devices,
  });
}
