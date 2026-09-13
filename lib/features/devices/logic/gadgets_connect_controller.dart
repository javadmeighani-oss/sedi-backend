import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import '../ble/sedi_ble_models.dart';
import '../ble/sedi_ble_permissions.dart';
import '../ble/sedi_ble_transport.dart';
import '../gateway/device_credential_store.dart';
import '../gateway/device_packet_relay.dart';
import '../gateway/gateway_install_id_store.dart';
import '../../../data/repositories/devices_repository.dart';

typedef BlePermissionRequester = Future<bool> Function();

/// Orchestrates G8 Connect → claim → gateway pair → subscribe/relay.
/// UI depends on this controller; BLE plugin stays behind [SediBleTransport].
class GadgetsConnectController {
  GadgetsConnectController({
    required DevicesRepository repository,
    required SediBleTransport transport,
    GatewayInstallIdStore? gatewayInstallIdStore,
    DeviceCredentialStore? credentialStore,
    DevicePacketRelay? packetRelay,
    BlePermissionRequester? requestBlePermissions,
    this.onPacketRelayed,
  })  : _repo = repository,
        _transport = transport,
        _gatewayStore = gatewayInstallIdStore ?? GatewayInstallIdStore(),
        _credentials = credentialStore ?? DeviceCredentialStore(),
        _relay = packetRelay,
        _requestBlePermissions =
            requestBlePermissions ?? SediBlePermissions.request;

  final DevicesRepository _repo;
  final SediBleTransport _transport;
  final GatewayInstallIdStore _gatewayStore;
  final DeviceCredentialStore _credentials;
  final DevicePacketRelay? _relay;
  final BlePermissionRequester _requestBlePermissions;
  final void Function(SediBleDeviceData data)? onPacketRelayed;

  SediBleTransportState transportState = SediBleTransportState.disconnected;
  String? connectedDeviceId;
  String? lastError;
  SediBleDeviceStatus? lastDeviceStatus;
  final List<SediBleDiscoveredDevice> discovered = [];

  StreamSubscription<SediBleTransportState>? _stateSub;
  StreamSubscription<SediBleDeviceData>? _dataSub;
  StreamSubscription<SediBleDeviceStatus>? _statusSub;
  StreamSubscription<SediBleDiscoveredDevice>? _scanSub;

  Map<String, SediBleTransportState> transportByDevice = {};

  SediBleTransportState transportFor(String deviceId) =>
      transportByDevice[deviceId] ?? SediBleTransportState.disconnected;

  Future<void> bindTransportListener() async {
    await _stateSub?.cancel();
    _stateSub = _transport.transportState.listen((s) {
      transportState = s;
      final id = connectedDeviceId;
      if (id != null) {
        transportByDevice[id] = s;
      }
    });
  }

  Future<bool> ensureBlePermission() => _requestBlePermissions();

  Future<List<SediBleDiscoveredDevice>> scan({
    Duration timeout = const Duration(seconds: 8),
  }) async {
    lastError = null;
    discovered.clear();
    final ok = await ensureBlePermission();
    if (!ok) {
      lastError =
          SediBlePermissions.lastOutcome ==
                  SediBlePermissionOutcome.permanentlyDenied
              ? 'BLE_PERMISSION_PERMANENTLY_DENIED'
              : 'BLE_PERMISSION_DENIED';
      return const [];
    }
    await _scanSub?.cancel();
    final completer = Completer<List<SediBleDiscoveredDevice>>();
    final seen = <String>{};
    _scanSub = _transport.scanForSediGadgets().listen(
      (d) {
        if (seen.add(d.remoteId)) {
          discovered.add(d);
        }
      },
      onError: (Object e) {
        lastError = e.toString();
        if (!completer.isCompleted) completer.complete(List.of(discovered));
      },
    );
    Future<void>.delayed(timeout, () async {
      await _scanSub?.cancel();
      _scanSub = null;
      if (!completer.isCompleted) completer.complete(List.of(discovered));
    });
    return completer.future;
  }

  Future<SediBleDeviceInfo?> connectAndReadInfo(String remoteId) async {
    lastError = null;
    try {
      await bindTransportListener();
      await _transport.connect(remoteId);
      final info = await _transport.readDeviceInfo();
      connectedDeviceId = info.deviceId;
      transportByDevice[info.deviceId] = SediBleTransportState.connected;
      lastDeviceStatus = await _transport.readDeviceStatus();
      return info;
    } catch (e) {
      lastError = e.toString();
      return null;
    }
  }

  /// CLAIM_CHALLENGE write + CLAIM_PROOF read → hex possession_proof.
  Future<String?> obtainPossessionProof() async {
    try {
      final nonce = _randomBytes(16);
      await _transport.writeClaimChallenge(nonce);
      final proof = await _transport.readClaimProof();
      return proof.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    } catch (e) {
      lastError = e.toString();
      return null;
    }
  }

  /// Claim via existing G1 contract — omit health_subject_id (server SELF).
  Future<bool> claimDevice({
    required String deviceId,
    required String possessionProof,
    required String setupCode,
    required String deviceCategory,
    String? userLabel,
  }) async {
    lastError = null;
    final gatewayId = await _gatewayStore.getOrCreate();
    final body = <String, dynamic>{
      'device_id': deviceId,
      'possession_proof': possessionProof,
      'setup_code': setupCode,
      'gateway_install_id': gatewayId,
      'device_category': deviceCategory.trim().toUpperCase(),
      if (deviceCategory.toUpperCase() == 'OTHER' &&
          userLabel != null &&
          userLabel.trim().isNotEmpty)
        'user_label': userLabel.trim(),
    };
    final resp = await _repo.claim(body: body);
    if (!resp.ok) {
      lastError = resp.errorMessage;
      return false;
    }
    return true;
  }

  Future<bool> pairGatewayAndStoreCredential(String deviceId) async {
    lastError = null;
    final gatewayId = await _gatewayStore.getOrCreate();
    final pair = await _repo.pairGateway(
      deviceId: deviceId,
      gatewayInstallId: gatewayId,
    );
    if (!pair.ok) {
      lastError = pair.errorMessage;
      return false;
    }
    final rotated = await _repo.rotateToken(deviceId: deviceId);
    if (!rotated.ok || rotated.data == null) {
      lastError = rotated.errorMessage ?? 'TOKEN_ROTATE_FAILED';
      return false;
    }
    final token = rotated.data!['token']?.toString();
    if (token == null || token.isEmpty) {
      lastError = 'TOKEN_MISSING';
      return false;
    }
    await _credentials.saveToken(deviceId: deviceId, token: token);
    return true;
  }

  Future<void> startDataSubscription(String deviceId) async {
    await _dataSub?.cancel();
    await _statusSub?.cancel();
    _dataSub = _transport.subscribeDeviceData().listen((data) async {
      onPacketRelayed?.call(data);
      final token = await _credentials.readToken(deviceId);
      final relay = _relay;
      if (token == null || relay == null) return;
      await relay.enqueueAndRelay(
        deviceId: deviceId,
        deviceToken: token,
        data: data,
      );
    });
    _statusSub = _transport.subscribeDeviceStatus().listen((s) {
      lastDeviceStatus = s;
    });
  }

  /// BLE disconnect + gateway disconnect. Device claim/history retained.
  Future<bool> manualDisconnect(String deviceId) async {
    lastError = null;
    await _dataSub?.cancel();
    await _statusSub?.cancel();
    _dataSub = null;
    _statusSub = null;
    await _transport.disconnect();
    transportByDevice[deviceId] = SediBleTransportState.disconnected;
    if (connectedDeviceId == deviceId) connectedDeviceId = null;
    transportState = SediBleTransportState.disconnected;
    final gatewayId = await _gatewayStore.peek();
    if (gatewayId != null) {
      final resp = await _repo.disconnectGateway(
        deviceId: deviceId,
        gatewayInstallId: gatewayId,
      );
      if (!resp.ok) {
        lastError = resp.errorMessage;
        return false;
      }
    }
    return true;
  }

  void dispose() {
    _stateSub?.cancel();
    _dataSub?.cancel();
    _statusSub?.cancel();
    _scanSub?.cancel();
    _transport.dispose();
  }

  static Uint8List _randomBytes(int n) {
    final r = Random.secure();
    return Uint8List.fromList(List.generate(n, (_) => r.nextInt(256)));
  }

  /// Test helper: hex encode without crypto deps.
  static String bytesToHex(List<int> bytes) =>
      bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();

  static List<int> challengeFromUtf8(String s) => utf8.encode(s);
}
