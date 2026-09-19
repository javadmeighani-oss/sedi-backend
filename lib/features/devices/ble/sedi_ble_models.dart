import 'dart:convert';

import 'sedi_ble_constants.dart';

/// BLE transport state only — never conflated with Device claim/active lifecycle.
enum SediBleTransportState {
  disconnected,
  connecting,
  connected,
  reconnecting,
  outOfRange,
}

class SediBleDiscoveredDevice {
  final String remoteId;
  final String? name;
  final int? rssi;

  const SediBleDiscoveredDevice({
    required this.remoteId,
    this.name,
    this.rssi,
  });
}

/// DEVICE_INFO UTF-8 JSON protocol v1.
class SediBleDeviceInfo {
  final int protocol;
  final String deviceId;
  final String? deviceType;
  final String? model;
  final String? firmwareVersion;

  const SediBleDeviceInfo({
    required this.protocol,
    required this.deviceId,
    this.deviceType,
    this.model,
    this.firmwareVersion,
  });

  factory SediBleDeviceInfo.fromJson(Map<String, dynamic> json) {
    final protocol = _asInt(json['protocol']) ?? SediBleConstants.protocolVersion;
    final deviceId = (json['device_id'] ?? '').toString().trim();
    if (deviceId.isEmpty) {
      throw const FormatException('DEVICE_INFO missing device_id');
    }
    return SediBleDeviceInfo(
      protocol: protocol,
      deviceId: deviceId,
      deviceType: json['device_type']?.toString(),
      model: json['model']?.toString(),
      firmwareVersion: json['firmware_version']?.toString(),
    );
  }

  static SediBleDeviceInfo parseUtf8(List<int> bytes) {
    final text = utf8.decode(bytes);
    final decoded = jsonDecode(text);
    if (decoded is! Map) {
      throw const FormatException('DEVICE_INFO must be JSON object');
    }
    return SediBleDeviceInfo.fromJson(Map<String, dynamic>.from(decoded));
  }
}

/// Gadget-prepared measurement fact. Mobile does not interpret clinically.
class SediBleMeasurement {
  final String type;
  final Map<String, dynamic> payload;
  /// STABLE | UNSTABLE when gadget supplies it — DEVICE_REPORTED only.
  final String? deviceReportedStability;

  const SediBleMeasurement({
    required this.type,
    required this.payload,
    this.deviceReportedStability,
  });

  factory SediBleMeasurement.fromJson(Map<String, dynamic> json) {
    final type = (json['type'] ?? json['observation_type'] ?? '').toString().trim();
    if (type.isEmpty) {
      throw const FormatException('measurement missing type');
    }
    final payload = <String, dynamic>{};
    if (json['payload'] is Map) {
      payload.addAll(Map<String, dynamic>.from(json['payload'] as Map));
    } else {
      for (final e in json.entries) {
        if (e.key == 'type' ||
            e.key == 'observation_type' ||
            e.key == 'stability' ||
            e.key == 'status' ||
            e.key == 'source_class') {
          continue;
        }
        payload[e.key] = e.value;
      }
    }
    final rawStability = json['stability'] ?? json['status'] ?? payload['stability'];
    String? stability;
    if (rawStability != null) {
      final s = rawStability.toString().trim().toUpperCase();
      if (s == 'STABLE' || s == 'UNSTABLE') {
        stability = s;
      }
    }
    return SediBleMeasurement(
      type: type,
      payload: payload,
      deviceReportedStability: stability,
    );
  }
}

/// DEVICE_DATA UTF-8 JSON protocol v1.
class SediBleDeviceData {
  final int protocol;
  final String packetId;
  final DateTime measuredAt;
  final List<SediBleMeasurement> measurements;
  /// Packet-level DEVICE_REPORTED stability when supplied by gadget.
  final String? deviceReportedStability;

  const SediBleDeviceData({
    required this.protocol,
    required this.packetId,
    required this.measuredAt,
    required this.measurements,
    this.deviceReportedStability,
  });

  factory SediBleDeviceData.fromJson(Map<String, dynamic> json) {
    final protocol = _asInt(json['protocol']) ?? SediBleConstants.protocolVersion;
    final packetId = (json['packet_id'] ?? json['client_packet_id'] ?? '')
        .toString()
        .trim();
    if (packetId.isEmpty) {
      throw const FormatException('DEVICE_DATA missing packet_id');
    }
    final measuredRaw = json['measured_at']?.toString();
    if (measuredRaw == null || measuredRaw.isEmpty) {
      throw const FormatException('DEVICE_DATA missing measured_at');
    }
    final measuredAt = DateTime.parse(measuredRaw).toUtc();
    final measurements = <SediBleMeasurement>[];
    final rawList = json['measurements'];
    if (rawList is List) {
      for (final item in rawList) {
        if (item is Map) {
          measurements.add(
            SediBleMeasurement.fromJson(Map<String, dynamic>.from(item)),
          );
        }
      }
    }
    final rawStability = json['stability'] ?? json['status'];
    String? stability;
    if (rawStability != null) {
      final s = rawStability.toString().trim().toUpperCase();
      if (s == 'STABLE' || s == 'UNSTABLE') {
        stability = s;
      }
    }
    return SediBleDeviceData(
      protocol: protocol,
      packetId: packetId,
      measuredAt: measuredAt,
      measurements: measurements,
      deviceReportedStability: stability,
    );
  }

  static SediBleDeviceData parseUtf8(List<int> bytes) {
    final text = utf8.decode(bytes);
    final decoded = jsonDecode(text);
    if (decoded is! Map) {
      throw const FormatException('DEVICE_DATA must be JSON object');
    }
    return SediBleDeviceData.fromJson(Map<String, dynamic>.from(decoded));
  }

  /// Preserve gadget STABLE/UNSTABLE as DEVICE_REPORTED — never invent.
  String? get preservedDeviceReportedStability {
    if (deviceReportedStability != null) return deviceReportedStability;
    for (final m in measurements) {
      if (m.deviceReportedStability != null) {
        return m.deviceReportedStability;
      }
    }
    return null;
  }
}

/// DEVICE_STATUS — device/transport facts only (not clinical authority).
class SediBleDeviceStatus {
  final int protocol;
  final int? batteryPercent;
  final bool? contactOk;
  final String? operatingStatus;
  final Map<String, dynamic> raw;

  const SediBleDeviceStatus({
    required this.protocol,
    this.batteryPercent,
    this.contactOk,
    this.operatingStatus,
    this.raw = const {},
  });

  factory SediBleDeviceStatus.fromJson(Map<String, dynamic> json) {
    return SediBleDeviceStatus(
      protocol: _asInt(json['protocol']) ?? SediBleConstants.protocolVersion,
      batteryPercent: _asInt(json['battery_percent'] ?? json['battery']),
      contactOk: json['contact_ok'] is bool
          ? json['contact_ok'] as bool
          : (json['contact'] is bool ? json['contact'] as bool : null),
      operatingStatus: json['operating_status']?.toString() ??
          json['status']?.toString(),
      raw: Map<String, dynamic>.from(json),
    );
  }

  static SediBleDeviceStatus parseUtf8(List<int> bytes) {
    final text = utf8.decode(bytes);
    final decoded = jsonDecode(text);
    if (decoded is! Map) {
      throw const FormatException('DEVICE_STATUS must be JSON object');
    }
    return SediBleDeviceStatus.fromJson(Map<String, dynamic>.from(decoded));
  }
}

int? _asInt(Object? v) {
  if (v == null) return null;
  if (v is int) return v;
  if (v is num) return v.toInt();
  return int.tryParse(v.toString());
}

/// Map plugin connection events → Sedi transport states (no claim semantics).
SediBleTransportState mapConnectionToTransportState({
  required bool isConnecting,
  required bool isConnected,
  required bool isReconnecting,
  required bool outOfRange,
}) {
  if (outOfRange) return SediBleTransportState.outOfRange;
  if (isReconnecting) return SediBleTransportState.reconnecting;
  if (isConnecting) return SediBleTransportState.connecting;
  if (isConnected) return SediBleTransportState.connected;
  return SediBleTransportState.disconnected;
}
