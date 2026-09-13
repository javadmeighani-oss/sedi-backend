/// Gadgets screen: backend Device classification SELF / OTHER / Unclassified.
/// BLE transport state is separate from platform status=active (never mapped).
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../../core/locale/sedi_locale_controller.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../data/dto/device_public_info.dart';
import '../../../../data/repositories/devices_repository.dart';
import '../../../gate3_interactive/presentation/widgets/a3_page_app_bar.dart';
import '../../ble/sedi_ble_models.dart';
import '../../ble/sedi_ble_transport.dart';
import '../../logic/devices_controller.dart';
import '../../logic/gadgets_connect_controller.dart';
import '../devices_l10n.dart';

class DevicesPage extends StatefulWidget {
  final DevicesController? controller;
  final GadgetsConnectController? connectController;

  const DevicesPage({
    super.key,
    this.controller,
    this.connectController,
  });

  @override
  State<DevicesPage> createState() => _DevicesPageState();
}

class _DevicesPageState extends State<DevicesPage> {
  late final DevicesController _controller;
  GadgetsConnectController? _connect;
  bool _loading = true;
  bool _connecting = false;

  DevicesL10n get _l10n =>
      DevicesL10n(SediLocaleController.instance.languageCode);

  @override
  void initState() {
    super.initState();
    _controller = widget.controller ?? DevicesController();
    _connect = widget.connectController;
    SediLocaleController.instance.addListener(_onLocale);
    _load();
  }

  @override
  void dispose() {
    SediLocaleController.instance.removeListener(_onLocale);
    if (widget.connectController == null) {
      _connect?.dispose();
    }
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

  GadgetsConnectController _ensureConnect() {
    return _connect ??= GadgetsConnectController(
      repository: DevicesRepository(),
      transport: ReactiveSediBleTransport(),
    );
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
            child: OutlinedButton(
              onPressed: _connecting ? null : () => _onConnectPressed(l10n),
              child: Text(_connecting ? l10n.scanning : l10n.connect),
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
    final ble = _connect?.transportFor(d.deviceId);
    final bleLabel = ble == null
        ? null
        : l10n.transportLabel(ble.name);
    final status = _connect?.lastDeviceStatus;
    final bits = <String>[
      d.deviceType,
      // Platform lifecycle only — never shown as BLE Connected.
      l10n.statusLabel(d.status),
      if (bleLabel != null) bleLabel,
      if (d.lastSeenAt != null) d.lastSeenAt!.toUtc().toIso8601String(),
      if (status?.batteryPercent != null)
        '${l10n.battery} ${status!.batteryPercent}%',
      if (status?.contactOk != null)
        '${l10n.contact} ${status!.contactOk}',
    ];
    final isBleConnected = ble == SediBleTransportState.connected &&
        _connect?.connectedDeviceId == d.deviceId;
    return ListTile(
      title: Text(d.displayName),
      subtitle: Text(
        bits.join(' · '),
        style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12),
      ),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (isBleConnected)
            TextButton(
              onPressed: _connecting
                  ? null
                  : () async {
                      setState(() => _connecting = true);
                      await _connect?.manualDisconnect(d.deviceId);
                      if (mounted) setState(() => _connecting = false);
                    },
              child: Text(l10n.disconnect),
            ),
          TextButton(
            onPressed: _controller.isActionInProgress
                ? null
                : () => _openPresentationEditor(d, l10n),
            child: Text(l10n.rename),
          ),
        ],
      ),
      dense: true,
    );
  }

  Future<void> _onConnectPressed(DevicesL10n l10n) async {
    setState(() => _connecting = true);
    final connect = _ensureConnect();
    try {
      final found = await connect.scan();
      if (!mounted) return;
      if (found.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(connect.lastError ?? l10n.noGadgets)),
        );
        return;
      }
      final selected = await showDialog<SediBleDiscoveredDevice>(
        context: context,
        builder: (ctx) => SimpleDialog(
          title: Text(l10n.selectDevice),
          children: [
            for (final d in found)
              SimpleDialogOption(
                onPressed: () => Navigator.pop(ctx, d),
                child: Text(d.name ?? d.remoteId),
              ),
          ],
        ),
      );
      if (selected == null || !mounted) return;

      final info = await connect.connectAndReadInfo(selected.remoteId);
      if (info == null || !mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(connect.lastError ?? 'connect failed')),
        );
        return;
      }

      final proof = await connect.obtainPossessionProof();
      if (proof == null || !mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(connect.lastError ?? 'proof failed')),
        );
        return;
      }

      final setupCtrl = TextEditingController();
      var category = 'SELF';
      final labelCtrl = TextEditingController();
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (ctx) => StatefulBuilder(
          builder: (ctx, setLocal) => AlertDialog(
            title: Text(info.deviceId),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: setupCtrl,
                  keyboardType: TextInputType.number,
                  maxLength: 4,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  decoration: InputDecoration(hintText: l10n.setupCodeHint),
                ),
                SegmentedButton<String>(
                  segments: [
                    ButtonSegment(
                        value: 'SELF', label: Text(l10n.selfCategory)),
                    ButtonSegment(
                        value: 'OTHER', label: Text(l10n.otherCategory)),
                  ],
                  selected: {category},
                  onSelectionChanged: (s) =>
                      setLocal(() => category = s.first),
                ),
                if (category == 'OTHER')
                  TextField(
                    controller: labelCtrl,
                    decoration: InputDecoration(hintText: l10n.labelHint),
                  ),
              ],
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: Text(l10n.cancel),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(ctx, true),
                child: Text(l10n.save),
              ),
            ],
          ),
        ),
      );
      if (confirmed != true || !mounted) {
        setupCtrl.dispose();
        labelCtrl.dispose();
        return;
      }

      final claimed = await connect.claimDevice(
        deviceId: info.deviceId,
        possessionProof: proof,
        setupCode: setupCtrl.text,
        deviceCategory: category,
        userLabel: labelCtrl.text,
      );
      setupCtrl.dispose();
      labelCtrl.dispose();
      if (!claimed || !mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(connect.lastError ?? 'claim failed')),
        );
        return;
      }

      final paired =
          await connect.pairGatewayAndStoreCredential(info.deviceId);
      if (!paired || !mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(connect.lastError ?? 'gateway failed')),
        );
        return;
      }

      await connect.startDataSubscription(info.deviceId);
      await _load();
    } finally {
      if (mounted) setState(() => _connecting = false);
    }
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
