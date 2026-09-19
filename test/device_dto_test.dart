import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/devices/ble/sedi_ble_constants.dart';
import 'package:sedi_app/features/devices/ble/sedi_ble_models.dart';
import 'package:sedi_app/features/devices/gateway/device_packet_mapper.dart';
import 'package:sedi_app/features/devices/gateway/gateway_install_id_store.dart';

import 'package:sedi_app/data/dto/device_register_request.dart';
import 'package:sedi_app/data/dto/device_public_info.dart';
import 'package:sedi_app/data/dto/devices_list_response.dart';
import 'package:sedi_app/data/dto/device_ingest_request.dart';
import 'package:sedi_app/data/dto/device_ingest_response.dart';

void main() {
  group('DeviceRegisterRequest', () {
    test('toJson includes device_id and optional device_type', () {
      final req = DeviceRegisterRequest(deviceId: 'Sedi001', deviceType: 'heart_rate');
      final j = req.toJson();
      expect(j['device_id'], 'Sedi001');
      expect(j['device_type'], 'heart_rate');
    });

    test('toJson omits device_type when null', () {
      final req = DeviceRegisterRequest(deviceId: 'Sedi002');
      final j = req.toJson();
      expect(j['device_id'], 'Sedi002');
      expect(j.containsKey('device_type'), isFalse);
    });
  });

  group('DevicePublicInfo.fromJson', () {
    test('parses backend device item', () {
      final json = {
        'device_id': 'Sedi001',
        'device_type': 'heart_rate',
        'status': 'active',
        'last_seen_at': '2025-02-09T12:00:00.000Z',
        'created_at': '2025-02-09T10:00:00.000Z',
        'revoked_at': null,
      };
      final d = DevicePublicInfo.fromJson(json);
      expect(d.deviceId, 'Sedi001');
      expect(d.deviceType, 'heart_rate');
      expect(d.status, 'active');
      expect(d.lastSeenAt, isNotNull);
      expect(d.revokedAt, isNull);
      expect(d.deviceCategory, isNull);
    });

    test('parses SELF category', () {
      final d = DevicePublicInfo.fromJson({
        'device_id': 'SEDI-ECG-1',
        'device_type': 'ECG',
        'status': 'active',
        'created_at': '2025-02-09T10:00:00Z',
        'device_category': 'SELF',
        'health_subject_id': 7,
      });
      expect(d.deviceCategory, 'SELF');
      expect(d.isSelfDevice, isTrue);
      expect(d.isOtherDevice, isFalse);
      expect(d.displayName, 'ECG');
    });

    test('parses OTHER + user_label', () {
      final d = DevicePublicInfo.fromJson({
        'device_id': 'SEDI-BP-1',
        'device_type': 'BP',
        'status': 'active',
        'created_at': '2025-02-09T10:00:00Z',
        'device_category': 'OTHER',
        'user_label': 'Mom cuff',
        'health_subject_id': 7,
      });
      expect(d.deviceCategory, 'OTHER');
      expect(d.userLabel, 'Mom cuff');
      expect(d.isOtherDevice, isTrue);
      expect(d.displayName, 'Mom cuff');
    });

    test('nullable legacy category does not infer from health_subject_id', () {
      final d = DevicePublicInfo.fromJson({
        'device_id': 'Legacy1',
        'device_type': 'heart_rate',
        'status': 'active',
        'created_at': '2025-02-09T10:00:00Z',
        'health_subject_id': 1,
      });
      expect(d.healthSubjectId, 1);
      expect(d.deviceCategory, isNull);
      expect(d.isSelfDevice, isFalse);
      expect(d.isOtherDevice, isFalse);
      expect(d.isUnclassifiedDevice, isTrue);
    });
  });

  group('DevicesListData.fromJson', () {
    test('parses devices array and count', () {
      final json = {
        'devices': [
          {'device_id': 'Sedi001', 'device_type': 'heart_rate', 'status': 'active', 'created_at': '2025-02-09T10:00:00Z'},
        ],
        'count': 1,
      };
      final data = DevicesListData.fromJson(json);
      expect(data.devices.length, 1);
      expect(data.devices.first.deviceId, 'Sedi001');
      expect(data.count, 1);
    });
  });

  group('DeviceIngestRequest', () {
    test('toJson includes user_id, event_type, payload', () {
      final req = DeviceIngestRequest(
        userId: 1,
        deviceId: 'Sedi001',
        eventType: 'heart_rate',
        payload: {'bpm': 82, 'quality': 'good'},
      );
      final j = req.toJson();
      expect(j['user_id'], 1);
      expect(j['device_id'], 'Sedi001');
      expect(j['event_type'], 'heart_rate');
      expect(j['payload'], {'bpm': 82, 'quality': 'good'});
    });
  });

  group('DeviceIngestResponse.fromJson', () {
    test('parses event_id and dedupe_key', () {
      final json = {'event_id': 123, 'dedupe_key': 'heart_rate:1:2025-02-09T10:30'};
      final r = DeviceIngestResponse.fromJson(json);
      expect(r.eventId, 123);
      expect(r.dedupeKey, 'heart_rate:1:2025-02-09T10:30');
    });
  });

  group('G3 BLE foundation', () {
    test('frozen UUIDs and scan filter authority', () {
      expect(
        SediBleConstants.primaryServiceUuid,
        'f2e6981f-4dc1-526d-a2c8-a043a1cddfa5',
      );
      expect(
        SediBleConstants.deviceInfoUuid,
        '467febf0-6629-59ed-a748-009d244af686',
      );
      expect(
        SediBleConstants.deviceDataUuid,
        'f144aeda-24e5-56df-a132-2e428b0dc1c2',
      );
      expect(
        SediBleConstants.deviceStatusUuid,
        '46b5efee-7522-5e4a-abbf-4d391478109b',
      );
      expect(
        File('lib/features/devices/ble/sedi_ble_transport.dart')
            .readAsStringSync()
            .contains('SediBleConstants.primaryServiceUuid'),
        isTrue,
      );
      expect(
        File('lib/features/devices/ble/sedi_ble_transport.dart')
            .readAsStringSync()
            .contains('withServices: scanServiceFilter'),
        isTrue,
      );
    });

    test('DEVICE_INFO / DEVICE_DATA parse; STABLE preserved DEVICE_REPORTED', () {
      final info = SediBleDeviceInfo.fromJson({
        'protocol': 1,
        'device_id': 'SEDI-HR-000000000001',
        'device_type': 'heart_rate',
        'model': 'G1',
        'firmware_version': '1.0.0',
      });
      expect(info.deviceId, 'SEDI-HR-000000000001');

      final data = SediBleDeviceData.fromJson({
        'protocol': 1,
        'packet_id': 'pkt-1',
        'measured_at': '2026-09-12T10:00:00Z',
        'measurements': [
          {'type': 'heart_rate', 'bpm': 72, 'stability': 'UNSTABLE'},
        ],
      });
      expect(data.packetId, 'pkt-1');
      expect(data.preservedDeviceReportedStability, 'UNSTABLE');
      expect(SediBleConstants.sourceClassDeviceReported, 'DEVICE_REPORTED');
    });

    test('no clinical inference helpers in BLE models', () {
      final src = File('lib/features/devices/ble/sedi_ble_models.dart').readAsStringSync();
      expect(src.contains('diagnose'), isFalse);
      expect(src.contains('threshold'), isFalse);
      expect(src.contains('health_subject'), isFalse);
      expect(
        mapConnectionToTransportState(
          isConnecting: false,
          isConnected: true,
          isReconnecting: false,
          outOfRange: false,
        ),
        SediBleTransportState.connected,
      );
      expect(
        mapConnectionToTransportState(
          isConnecting: false,
          isConnected: false,
          isReconnecting: true,
          outOfRange: false,
        ),
        SediBleTransportState.reconnecting,
      );
    });
  });

  group('G4 packet mapping', () {
    test('maps to /device/packet body without user_id/health_subject_id', () {
      final data = SediBleDeviceData.fromJson({
        'protocol': 1,
        'packet_id': 'pkt-map-1',
        'measured_at': '2026-09-12T10:00:00Z',
        'stability': 'STABLE',
        'measurements': [
          {'type': 'heart_rate', 'bpm': 70},
        ],
      });
      final body = DevicePacketMapper.toPacketBody(
        data: data,
        gatewayInstallId: 'gateway-install-abcdefgh',
      );
      expect(body['client_packet_id'], 'pkt-map-1');
      expect(body['transport'], 'bluetooth');
      expect(body['gateway_install_id'], 'gateway-install-abcdefgh');
      expect(body.containsKey('user_id'), isFalse);
      expect(body.containsKey('health_subject_id'), isFalse);
      final obs = (body['observations'] as List).cast<Map>();
      expect(
        obs.any((o) => o['observation_type'] == 'device_reported_vital_status'),
        isTrue,
      );
      final statusObs = obs.firstWhere(
        (o) => o['observation_type'] == 'device_reported_vital_status',
      );
      expect(statusObs['payload']['status'], 'STABLE');
      expect(statusObs['payload']['source_class'], 'DEVICE_REPORTED');
    });

    test('DevicesRepository canonical packet endpoint only for G4 relay', () {
      final src = File('lib/data/repositories/devices_repository.dart').readAsStringSync();
      expect(src.contains("'/device/packet'"), isTrue);
      expect(src.contains('postDevicePacket'), isTrue);
      expect(src.contains('gateway/pair'), isTrue);
      expect(src.contains('/device/ingest'), isFalse);
      expect(src.contains('/data/upload'), isFalse);
    });

    test('gateway_install_id entropy length', () {
      final id = GatewayInstallIdStore.generateHighEntropyInstallId();
      expect(id.length, 64);
    });
  });
}
