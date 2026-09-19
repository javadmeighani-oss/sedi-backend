import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/network/api_response.dart';
import 'package:sedi_app/data/dto/device_public_info.dart';
import 'package:sedi_app/data/dto/devices_list_response.dart';
import 'package:sedi_app/data/repositories/devices_repository.dart';
import 'package:sedi_app/features/devices/logic/devices_controller.dart';
import 'package:sedi_app/features/devices/presentation/devices_l10n.dart';
import 'dart:io';

class FakeDevicesRepository extends DevicesRepository {
  FakeDevicesRepository() : super(baseUrl: 'http://fake');

  int listCallCount = 0;
  bool revokeCalled = false;
  bool rotateTokenCalled = false;
  bool presentationCalled = false;
  String? lastPresentationCategory;
  String? lastPresentationLabel;
  List<DevicePublicInfo> listDevices = const [];

  @override
  Future<ApiResponse<DevicesListData?>> list() async {
    listCallCount++;
    return ApiResponse(
      ok: true,
      data: DevicesListData(devices: listDevices, count: listDevices.length),
    );
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
    rotateTokenCalled = true;
    return const ApiResponse(ok: true, data: {});
  }

  @override
  Future<ApiResponse<Map<String, dynamic>?>> updatePresentation({
    required String deviceId,
    required String deviceCategory,
    String? userLabel,
  }) async {
    presentationCalled = true;
    lastPresentationCategory = deviceCategory;
    lastPresentationLabel = userLabel;
    return const ApiResponse(ok: true, data: {});
  }
}

void main() {
  group('DevicesController JWT actions', () {
    test('loadDevices calls repo.list without profile userId', () async {
      final fake = FakeDevicesRepository();
      final controller = DevicesController(repo: fake);
      await controller.loadDevices();
      expect(fake.listCallCount, 1);
      expect(controller.errorMessage, isNull);
    });

    test('revokeDevice calls repo.revoke then loadDevices', () async {
      final fake = FakeDevicesRepository();
      final controller = DevicesController(repo: fake);
      await controller.revokeDevice('device-1');
      expect(fake.revokeCalled, isTrue);
      expect(fake.listCallCount, greaterThanOrEqualTo(1));
    });

    test('rotateDeviceToken calls repo.rotateToken then loadDevices', () async {
      final fake = FakeDevicesRepository();
      final controller = DevicesController(repo: fake);
      await controller.rotateDeviceToken('device-2');
      expect(fake.rotateTokenCalled, isTrue);
      expect(fake.listCallCount, greaterThanOrEqualTo(1));
    });

    test('updateDevicePresentation PATCH then reload; reentrancy guard',
        () async {
      final fake = FakeDevicesRepository();
      final controller = DevicesController(repo: fake);
      final ok = await controller.updateDevicePresentation(
        deviceId: 'd1',
        deviceCategory: 'OTHER',
        userLabel: 'Mom BP',
      );
      expect(ok, isTrue);
      expect(fake.presentationCalled, isTrue);
      expect(fake.lastPresentationCategory, 'OTHER');
      expect(fake.lastPresentationLabel, 'Mom BP');
      expect(fake.listCallCount, greaterThanOrEqualTo(1));

      controller.isActionInProgress = true;
      final blocked = await controller.updateDevicePresentation(
        deviceId: 'd1',
        deviceCategory: 'SELF',
      );
      expect(blocked, isFalse);
      expect(controller.errorMessage, 'Please wait.');
    });

    test('OTHER without label rejected client-side', () async {
      final fake = FakeDevicesRepository();
      final controller = DevicesController(repo: fake);
      final ok = await controller.updateDevicePresentation(
        deviceId: 'd1',
        deviceCategory: 'OTHER',
        userLabel: '  ',
      );
      expect(ok, isFalse);
      expect(fake.presentationCalled, isFalse);
    });
  });

  group('DevicesController category grouping', () {
    test('self/other from device_category only; null not inferred', () async {
      final now = DateTime.utc(2026, 1, 1);
      final fake = FakeDevicesRepository()
        ..listDevices = [
          DevicePublicInfo(
            deviceId: 'self-1',
            deviceType: 'ECG',
            status: 'active',
            createdAt: now,
            healthSubjectId: 99,
            deviceCategory: 'SELF',
          ),
          DevicePublicInfo(
            deviceId: 'other-1',
            deviceType: 'BP',
            status: 'active',
            createdAt: now,
            healthSubjectId: 99,
            deviceCategory: 'OTHER',
            userLabel: 'Kitchen',
          ),
          DevicePublicInfo(
            deviceId: 'legacy-1',
            deviceType: 'SpO2',
            status: 'active',
            createdAt: now,
            healthSubjectId: 1,
            deviceCategory: null,
          ),
        ];
      final controller = DevicesController(repo: fake);
      await controller.loadDevices();
      expect(controller.selfDevices.map((d) => d.deviceId), ['self-1']);
      expect(controller.otherDevices.map((d) => d.deviceId), ['other-1']);
      expect(controller.unclassifiedDevices.map((d) => d.deviceId),
          ['legacy-1']);
      expect(controller.unclassifiedDevices.first.isSelfDevice, isFalse);
      expect(controller.unclassifiedDevices.first.isOtherDevice, isFalse);
    });
  });

  group('G4/G5 relay contract source', () {
    test('relay uses ACCEPTED/DUPLICATE removal and permanent auth set', () {
      final src = File(
        'lib/features/devices/gateway/device_packet_relay.dart',
      ).readAsStringSync();
      expect(src.contains('PacketRelayAck.accepted'), isTrue);
      expect(src.contains('PacketRelayAck.duplicate'), isTrue);
      expect(src.contains('permanentAckCodes'), isTrue);
      expect(src.contains('GATEWAY_AUTH_REJECTED'), isTrue);
      expect(src.contains('/device/ingest'), isFalse);
      expect(src.contains('/data/upload'), isFalse);
    });

    test('gateway install id uses flutter_secure_storage', () {
      final src = File(
        'lib/features/devices/gateway/gateway_install_id_store.dart',
      ).readAsStringSync();
      expect(src.contains('FlutterSecureStorage'), isTrue);
      expect(src.contains('sedi_gateway_install_id_v1'), isTrue);
    });
  });

  group('G8 connect orchestration', () {
    test('claim omits health_subject_id; disconnect keeps device claim path', () {
      final repoSrc = File('lib/data/repositories/devices_repository.dart')
          .readAsStringSync();
      expect(repoSrc.contains("'/devices/claim'"), isTrue);
      expect(repoSrc.contains("'user' '_id'"), isTrue);
      expect(repoSrc.contains('disconnectGateway'), isTrue);

      final connectSrc = File(
        'lib/features/devices/logic/gadgets_connect_controller.dart',
      ).readAsStringSync();
      expect(connectSrc.contains('manualDisconnect'), isTrue);
      expect(connectSrc.contains('pairGateway'), isTrue);
      expect(connectSrc.contains('obtainPossessionProof'), isTrue);
      expect(connectSrc.contains('.revoke('), isFalse);
      expect(connectSrc.contains('diagnose'), isFalse);
      expect(connectSrc.contains('threshold'), isFalse);
    });

    test('transport labels separate from platform active', () {
      final l10n = DevicesL10n('en');
      expect(l10n.transportLabel('connected'), 'Connected');
      expect(l10n.statusLabel('active'), isNot(l10n.bleConnected));
      expect(l10n.connect, 'Connect');
      expect(DevicesL10n('fa').connect, isNotEmpty);
      expect(DevicesL10n('ar').connect, isNotEmpty);
    });
  });
}