import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/network/api_response.dart';
import 'package:sedi_app/data/repositories/devices_repository.dart';
import 'package:sedi_app/features/devices/ble/sedi_ble_models.dart';
import 'package:sedi_app/features/devices/ble/sedi_ble_transport.dart';
import 'package:sedi_app/features/devices/gateway/gateway_install_id_store.dart';
import 'package:sedi_app/features/devices/logic/gadgets_connect_controller.dart';
import 'package:sedi_app/features/devices/gateway/device_credential_store.dart';


class _MemorySecure {
  final map = <String, String>{};
}

class _FakeGatewayStore extends GatewayInstallIdStore {
  _FakeGatewayStore() : super();
  String? _id;
  @override
  Future<String> getOrCreate() async {
    _id ??= GatewayInstallIdStore.generateHighEntropyInstallId();
    return _id!;
  }
  @override
  Future<String?> peek() async => _id;
}

class _FakeCredStore extends DeviceCredentialStore {
  final map = <String, String>{};
  @override
  Future<void> saveToken({required String deviceId, required String token}) async {
    map[deviceId] = token;
  }
  @override
  Future<String?> readToken(String deviceId) async => map[deviceId];
}

class _FakeBle implements SediBleTransport {
  final _state = StreamController<SediBleTransportState>.broadcast();
  SediBleTransportState current = SediBleTransportState.disconnected;

  @override
  Stream<SediBleTransportState> get transportState => _state.stream;

  @override
  Stream<SediBleDiscoveredDevice> scanForSediGadgets() async* {
    yield const SediBleDiscoveredDevice(remoteId: 'aa:bb', name: 'SEDI');
  }

  @override
  Future<void> connect(String remoteId) async {
    current = SediBleTransportState.connected;
    _state.add(current);
  }

  @override
  Future<void> disconnect() async {
    current = SediBleTransportState.disconnected;
    _state.add(current);
  }

  @override
  Future<SediBleDeviceInfo> readDeviceInfo() async => const SediBleDeviceInfo(
        protocol: 1,
        deviceId: 'SEDI-HR-000000000099',
        deviceType: 'heart_rate',
      );

  @override
  Stream<SediBleDeviceData> subscribeDeviceData() => const Stream.empty();

  @override
  Stream<SediBleDeviceStatus> subscribeDeviceStatus() => const Stream.empty();

  @override
  Future<SediBleDeviceStatus?> readDeviceStatus() async =>
      const SediBleDeviceStatus(protocol: 1, batteryPercent: 80, contactOk: true);

  @override
  Future<void> writeClaimChallenge(List<int> challengeNonce) async {}

  @override
  Future<List<int>> readClaimProof() async => [1, 2, 3, 4];

  @override
  void dispose() {
    _state.close();
  }
}

class _FakeRepo extends DevicesRepository {
  _FakeRepo() : super(baseUrl: 'http://fake');

  Map<String, dynamic>? lastClaimBody;
  bool pairCalled = false;
  bool disconnectCalled = false;
  bool revokeCalled = false;
  bool rotateCalled = false;

  @override
  Future<ApiResponse<Map<String, dynamic>?>> claim({
    required Map<String, dynamic> body,
  }) async {
    lastClaimBody = body;
    return const ApiResponse(ok: true, data: {});
  }

  @override
  Future<ApiResponse<Map<String, dynamic>?>> pairGateway({
    required String deviceId,
    required String gatewayInstallId,
  }) async {
    pairCalled = true;
    return const ApiResponse(ok: true, data: {});
  }

  @override
  Future<ApiResponse<Map<String, dynamic>?>> disconnectGateway({
    required String deviceId,
    required String gatewayInstallId,
  }) async {
    disconnectCalled = true;
    return const ApiResponse(ok: true, data: {});
  }

  @override
  Future<ApiResponse<Map<String, dynamic>?>> revoke({
    required String deviceId,
  }) async {
    revokeCalled = true;
    return const ApiResponse(ok: true, data: {});
  }

  @override
  Future<ApiResponse<Map<String, dynamic>?>> rotateToken({
    required String deviceId,
  }) async {
    rotateCalled = true;
    return const ApiResponse(ok: true, data: {'token': 'dev-token-1'});
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('G8 SELF connect claim/pair; disconnect revokes gateway not Device',
      () async {
    final repo = _FakeRepo();
    final ble = _FakeBle();
    final c = GadgetsConnectController(
      repository: repo,
      transport: ble,
      gatewayInstallIdStore: _FakeGatewayStore(),
      credentialStore: _FakeCredStore(),
      requestBlePermissions: () async => true,
    );

    final found = await c.scan(timeout: const Duration(milliseconds: 50));
    expect(found, isNotEmpty);
    final info = await c.connectAndReadInfo(found.first.remoteId);
    expect(info?.deviceId, 'SEDI-HR-000000000099');
    final proof = await c.obtainPossessionProof();
    expect(proof, isNotNull);

    final claimed = await c.claimDevice(
      deviceId: info!.deviceId,
      possessionProof: proof!,
      setupCode: '1234',
      deviceCategory: 'SELF',
    );
    expect(claimed, isTrue);
    expect(repo.lastClaimBody!.containsKey('health_subject_id'), isFalse);
    expect(repo.lastClaimBody!['device_category'], 'SELF');

    expect(await c.pairGatewayAndStoreCredential(info.deviceId), isTrue);
    expect(repo.pairCalled, isTrue);
    expect(repo.rotateCalled, isTrue);

    expect(await c.manualDisconnect(info.deviceId), isTrue);
    expect(repo.disconnectCalled, isTrue);
    expect(repo.revokeCalled, isFalse);
    expect(c.transportFor(info.deviceId), SediBleTransportState.disconnected);
    c.dispose();
  });

  test('G8 OTHER requires label field when provided', () async {
    final repo = _FakeRepo();
    final c = GadgetsConnectController(
      repository: repo,
      transport: _FakeBle(),
      gatewayInstallIdStore: _FakeGatewayStore(),
      credentialStore: _FakeCredStore(),
      requestBlePermissions: () async => true,
    );
    await c.claimDevice(
      deviceId: 'SEDI-HR-1',
      possessionProof: 'abcd',
      setupCode: '9999',
      deviceCategory: 'OTHER',
      userLabel: 'Mom BP',
    );
    expect(repo.lastClaimBody!['device_category'], 'OTHER');
    expect(repo.lastClaimBody!['user_label'], 'Mom BP');
    c.dispose();
  });
}
