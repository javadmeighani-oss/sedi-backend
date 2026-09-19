import 'dart:async';

import 'package:flutter_reactive_ble/flutter_reactive_ble.dart';

import 'sedi_ble_constants.dart';
import 'sedi_ble_models.dart';

/// UI/controllers depend on this abstraction — not on plugin calls directly.
abstract class SediBleTransport {
  Stream<SediBleTransportState> get transportState;

  /// Scan filtered by frozen Sedi Primary Service UUID only.
  Stream<SediBleDiscoveredDevice> scanForSediGadgets();

  Future<void> connect(String remoteId);

  Future<void> disconnect();

  Future<SediBleDeviceInfo> readDeviceInfo();

  Stream<SediBleDeviceData> subscribeDeviceData();

  Stream<SediBleDeviceStatus> subscribeDeviceStatus();

  /// Optional READ of DEVICE_STATUS after connect.
  Future<SediBleDeviceStatus?> readDeviceStatus();

  /// Write CLAIM_CHALLENGE when G1 possession flow requires it.
  Future<void> writeClaimChallenge(List<int> challengeNonce);

  Future<List<int>> readClaimProof();

  void dispose();
}

/// Minimal flutter_reactive_ble-backed transport.
///
/// OPEN_FINDING: true Android CompanionDeviceManager / background association
/// is not implemented in this Gate — reconnect is in-process lifecycle only.
class ReactiveSediBleTransport implements SediBleTransport {
  ReactiveSediBleTransport({FlutterReactiveBle? ble})
      : _ble = ble ?? FlutterReactiveBle();

  final FlutterReactiveBle _ble;
  final _stateCtrl = StreamController<SediBleTransportState>.broadcast();
  SediBleTransportState _state = SediBleTransportState.disconnected;
  String? _remoteId;
  StreamSubscription<ConnectionStateUpdate>? _connSub;
  StreamSubscription<DiscoveredDevice>? _scanSub;
  bool _intentionalDisconnect = false;

  static final Uuid primaryService =
      Uuid.parse(SediBleConstants.primaryServiceUuid);
  static final Uuid deviceInfoChar =
      Uuid.parse(SediBleConstants.deviceInfoUuid);
  static final Uuid deviceDataChar =
      Uuid.parse(SediBleConstants.deviceDataUuid);
  static final Uuid deviceStatusChar =
      Uuid.parse(SediBleConstants.deviceStatusUuid);
  static final Uuid claimChallengeChar =
      Uuid.parse(SediBleConstants.claimChallengeUuid);
  static final Uuid claimProofChar =
      Uuid.parse(SediBleConstants.claimProofUuid);

  /// Authority: scan filter is Primary Service UUID only.
  static List<Uuid> get scanServiceFilter => [primaryService];

  @override
  Stream<SediBleTransportState> get transportState => _stateCtrl.stream;

  SediBleTransportState get currentState => _state;

  void _emit(SediBleTransportState next) {
    _state = next;
    if (!_stateCtrl.isClosed) {
      _stateCtrl.add(next);
    }
  }

  @override
  Stream<SediBleDiscoveredDevice> scanForSediGadgets() {
    final controller = StreamController<SediBleDiscoveredDevice>();
    _scanSub?.cancel();
    _scanSub = _ble
        .scanForDevices(withServices: scanServiceFilter, scanMode: ScanMode.balanced)
        .listen(
      (d) {
        if (!controller.isClosed) {
          controller.add(
            SediBleDiscoveredDevice(
              remoteId: d.id,
              name: d.name.isEmpty ? null : d.name,
              rssi: d.rssi,
            ),
          );
        }
      },
      onError: controller.addError,
      onDone: controller.close,
    );
    controller.onCancel = () async {
      await _scanSub?.cancel();
      _scanSub = null;
    };
    return controller.stream;
  }

  @override
  Future<void> connect(String remoteId) async {
    await _scanSub?.cancel();
    _scanSub = null;
    _intentionalDisconnect = false;
    _remoteId = remoteId;
    _emit(SediBleTransportState.connecting);
    await _connSub?.cancel();
    final completer = Completer<void>();
    _connSub = _ble
        .connectToDevice(
      id: remoteId,
      connectionTimeout: const Duration(seconds: 20),
    )
        .listen(
      (update) {
        switch (update.connectionState) {
          case DeviceConnectionState.connecting:
            _emit(SediBleTransportState.connecting);
            break;
          case DeviceConnectionState.connected:
            _emit(SediBleTransportState.connected);
            if (!completer.isCompleted) completer.complete();
            break;
          case DeviceConnectionState.disconnecting:
            break;
          case DeviceConnectionState.disconnected:
            if (_intentionalDisconnect) {
              _emit(SediBleTransportState.disconnected);
            } else if (_remoteId != null) {
              _emit(SediBleTransportState.reconnecting);
              _scheduleReconnect();
            } else {
              _emit(SediBleTransportState.disconnected);
            }
            break;
        }
      },
      onError: (Object e, StackTrace st) {
        _emit(SediBleTransportState.outOfRange);
        if (!completer.isCompleted) {
          completer.completeError(e, st);
        }
      },
    );
    await completer.future;
  }

  void _scheduleReconnect() {
    final id = _remoteId;
    if (id == null || _intentionalDisconnect) return;
    // Minimal in-process reconnect — no CompanionDeviceManager subsystem.
    Future<void>.delayed(const Duration(seconds: 2), () async {
      if (_intentionalDisconnect || _remoteId != id) return;
      if (_state == SediBleTransportState.connected) return;
      try {
        await connect(id);
      } catch (_) {
        _emit(SediBleTransportState.outOfRange);
      }
    });
  }

  @override
  Future<void> disconnect() async {
    _intentionalDisconnect = true;
    await _connSub?.cancel();
    _connSub = null;
    _remoteId = null;
    _emit(SediBleTransportState.disconnected);
  }

  QualifiedCharacteristic _char(Uuid characteristic) {
    final id = _remoteId;
    if (id == null) {
      throw StateError('Not connected');
    }
    return QualifiedCharacteristic(
      serviceId: primaryService,
      characteristicId: characteristic,
      deviceId: id,
    );
  }

  @override
  Future<SediBleDeviceInfo> readDeviceInfo() async {
    final bytes = await _ble.readCharacteristic(_char(deviceInfoChar));
    return SediBleDeviceInfo.parseUtf8(bytes);
  }

  @override
  Stream<SediBleDeviceData> subscribeDeviceData() {
    return _ble.subscribeToCharacteristic(_char(deviceDataChar)).map(
          SediBleDeviceData.parseUtf8,
        );
  }

  @override
  Stream<SediBleDeviceStatus> subscribeDeviceStatus() {
    return _ble.subscribeToCharacteristic(_char(deviceStatusChar)).map(
          SediBleDeviceStatus.parseUtf8,
        );
  }

  @override
  Future<SediBleDeviceStatus?> readDeviceStatus() async {
    try {
      final bytes = await _ble.readCharacteristic(_char(deviceStatusChar));
      return SediBleDeviceStatus.parseUtf8(bytes);
    } catch (_) {
      return null;
    }
  }

  @override
  Future<void> writeClaimChallenge(List<int> challengeNonce) async {
    await _ble.writeCharacteristicWithResponse(
      _char(claimChallengeChar),
      value: challengeNonce,
    );
  }

  @override
  Future<List<int>> readClaimProof() async {
    return _ble.readCharacteristic(_char(claimProofChar));
  }

  @override
  void dispose() {
    _intentionalDisconnect = true;
    _scanSub?.cancel();
    _connSub?.cancel();
    _stateCtrl.close();
  }
}
