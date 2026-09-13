/// Gadgets screen: backend Device classification SELF / OTHER / Unclassified.
/// No HealthSubject grouping. No BLE transport state. No active→Connected mapping.
import 'package:flutter/material.dart';

import '../../../../core/locale/sedi_locale_controller.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../data/dto/device_public_info.dart';
import '../../../gate3_interactive/presentation/widgets/a3_page_app_bar.dart';
import '../../logic/devices_controller.dart';
import '../devices_l10n.dart';

class DevicesPage extends StatefulWidget {
  const DevicesPage({super.key});

  @override
  State<DevicesPage> createState() => _DevicesPageState();
}

class _DevicesPageState extends State<DevicesPage> {
  final DevicesController _controller = DevicesController();
  bool _loading = true;

  DevicesL10n get _l10n =>
      DevicesL10n(SediLocaleController.instance.languageCode);

  @override
  void initState() {
    super.initState();
    SediLocaleController.instance.addListener(_onLocale);
    _load();
  }

  @override
  void dispose() {
    SediLocaleController.instance.removeListener(_onLocale);
    super.dispose();
  }

  void _onLocale() {
    if (mounted) setState(() {});
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    await _controller.loadDevices();
    if (mounted) setState(() => _loading = false);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = _l10n;
    final groups = <_DeviceGroup>[
      _DeviceGroup(title: l10n.myGadgets, devices: _controller.selfDevices),
      _DeviceGroup(title: l10n.otherGadgets, devices: _controller.otherDevices),
      if (_controller.unclassifiedDevices.isNotEmpty)
        _DeviceGroup(
          title: l10n.unclassified,
          devices: _controller.unclassifiedDevices,
        ),
    ];

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
                child: CircularProgressIndicator(color: AppTheme.pistachioGreen),
              ),
            )
          else if (_controller.devices.isEmpty)
            Padding(
              padding: const EdgeInsets.all(24),
              child: Text(
                l10n.noGadgets,
                style: const TextStyle(color: AppTheme.textSecondary),
              ),
            )
          else
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
                Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  child: Text(
                    l10n.noGadgets,
                    style: const TextStyle(color: AppTheme.textSecondary),
                  ),
                )
              else
                for (final d in g.devices) _deviceRow(d, l10n),
            ],
          if (_controller.errorMessage != null)
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(
                _controller.errorMessage!,
                style: const TextStyle(color: Colors.redAccent, fontSize: 13),
              ),
            ),
          const SizedBox(height: 16),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: IgnorePointer(
              child: Opacity(
                opacity: 0.55,
                child: OutlinedButton(
                  onPressed: () {},
                  child: Text(l10n.connectComingSoon),
                ),
              ),
            ),
          ),
        ],
      ),
    );

    Widget page = Scaffold(
      backgroundColor: AppTheme.backgroundWhite,
      appBar: A3PageAppBar(
        title: Text(l10n.title),
        backgroundColor: AppTheme.backgroundWhite,
        foregroundColor: AppTheme.primaryBlack,
      ),
      body: body,
    );

    if (SediLocaleController.instance.isRtl) {
      page = Directionality(
        textDirection: TextDirection.rtl,
        child: page,
      );
    }
    return page;
  }

  Widget _deviceRow(DevicePublicInfo d, DevicesL10n l10n) {
    return ListTile(
      title: Text(d.displayName),
      subtitle: Text(
        '${d.deviceType} · ${l10n.statusLabel(d.status)}',
        style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12),
      ),
      trailing: TextButton(
        onPressed: _controller.isActionInProgress
            ? null
            : () => _openPresentationEditor(d, l10n),
        child: Text(l10n.rename),
      ),
      dense: true,
    );
  }

  Future<void> _openPresentationEditor(
    DevicePublicInfo device,
    DevicesL10n l10n,
  ) async {
    var category = device.isOtherDevice
        ? 'OTHER'
        : (device.isSelfDevice ? 'SELF' : 'SELF');
    final labelCtrl = TextEditingController(text: device.userLabel ?? '');

    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setLocal) {
            return AlertDialog(
              title: Text(l10n.rename),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Align(
                    alignment: AlignmentDirectional.centerStart,
                    child: Text(l10n.category),
                  ),
                  const SizedBox(height: 8),
                  SegmentedButton<String>(
                    segments: [
                      ButtonSegment(
                        value: 'SELF',
                        label: Text(l10n.selfCategory),
                      ),
                      ButtonSegment(
                        value: 'OTHER',
                        label: Text(l10n.otherCategory),
                      ),
                    ],
                    selected: {category},
                    onSelectionChanged: (s) {
                      setLocal(() => category = s.first);
                    },
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: labelCtrl,
                    maxLength: 80,
                    decoration: InputDecoration(hintText: l10n.labelHint),
                  ),
                ],
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(ctx).pop(false),
                  child: Text(l10n.cancel),
                ),
                FilledButton(
                  onPressed: () => Navigator.of(ctx).pop(true),
                  child: Text(l10n.save),
                ),
              ],
            );
          },
        );
      },
    );

    if (saved != true || !mounted) {
      labelCtrl.dispose();
      return;
    }

    final ok = await _controller.updateDevicePresentation(
      deviceId: device.deviceId,
      deviceCategory: category,
      userLabel: labelCtrl.text,
    );
    labelCtrl.dispose();
    if (!mounted) return;
    setState(() {});
    final messenger = ScaffoldMessenger.of(context);
    if (ok) {
      messenger.showSnackBar(SnackBar(content: Text(l10n.presentationUpdated)));
    } else if (_controller.errorMessage != null) {
      messenger.showSnackBar(SnackBar(content: Text(_controller.errorMessage!)));
    }
  }
}

class _DeviceGroup {
  final String title;
  final List<DevicePublicInfo> devices;

  const _DeviceGroup({
    required this.title,
    required this.devices,
  });
}
