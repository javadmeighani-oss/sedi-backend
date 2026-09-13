import '../ble/sedi_ble_constants.dart';
import '../ble/sedi_ble_models.dart';

/// Maps prepared BLE DEVICE_DATA → canonical POST /device/packet body.
/// Never sends user_id / health_subject_id / caregiver identity.
class DevicePacketMapper {
  DevicePacketMapper._();

  static Map<String, dynamic> toPacketBody({
    required SediBleDeviceData data,
    required String gatewayInstallId,
    String? firmwareVersion,
    DateTime? gatewayReceivedAt,
  }) {
    final observations = <Map<String, dynamic>>[];

    for (final m in data.measurements) {
      final type = _normalizeObservationType(m.type);
      if (type == null) continue;
      if (type == 'device_reported_vital_status') {
        final status = m.deviceReportedStability ??
            m.payload['status']?.toString().toUpperCase();
        if (status == 'STABLE' || status == 'UNSTABLE') {
          observations.add({
            'observation_type': 'device_reported_vital_status',
            'payload': {
              'status': status,
              'source_class': SediBleConstants.sourceClassDeviceReported,
            },
          });
        }
        continue;
      }
      observations.add({
        'observation_type': type,
        'payload': Map<String, dynamic>.from(m.payload),
      });
    }

    final stability = data.preservedDeviceReportedStability;
    if (stability != null) {
      final already = observations.any(
        (o) => o['observation_type'] == 'device_reported_vital_status',
      );
      if (!already) {
        observations.add({
          'observation_type': 'device_reported_vital_status',
          'payload': {
            'status': stability,
            'source_class': SediBleConstants.sourceClassDeviceReported,
          },
        });
      }
    }

    return {
      'client_packet_id': data.packetId,
      'measured_at': data.measuredAt.toUtc().toIso8601String(),
      'gateway_received_at':
          (gatewayReceivedAt ?? DateTime.now().toUtc()).toIso8601String(),
      'transport': 'bluetooth',
      'gateway_install_id': gatewayInstallId,
      if (firmwareVersion != null && firmwareVersion.isNotEmpty)
        'firmware_version': firmwareVersion,
      'observations': observations,
      // Explicit: no user_id / health_subject_id — server attribution only.
    };
  }

  static String? _normalizeObservationType(String raw) {
    final t = raw.trim().toLowerCase();
    switch (t) {
      case 'hr':
      case 'heart_rate':
        return 'heart_rate';
      case 'bp':
      case 'blood_pressure':
        return 'blood_pressure';
      case 'spo2':
        return 'spo2';
      case 'temperature':
      case 'temp':
        return 'temperature';
      case 'glucose':
        return 'glucose';
      case 'device_reported_vital_status':
      case 'vital_status':
        return 'device_reported_vital_status';
      case 'device_reported_cardiac_event':
      case 'cardiac_event':
        return 'device_reported_cardiac_event';
      default:
        return t.isEmpty ? null : t;
    }
  }
}
