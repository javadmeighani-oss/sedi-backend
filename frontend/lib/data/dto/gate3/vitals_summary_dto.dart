class VitalReadingDto {

  final dynamic value;

  final String? unit;

  final String? recordedAt;

  final String? receivedAt;

  final String? source;

  final String? sourceDeviceId;

  final String? freshness;

  final String? quality;

  final int? systolic;

  final int? diastolic;

  final bool? monitoringAvailable;

  final bool? signalAvailable;



  const VitalReadingDto({

    this.value,

    this.unit,

    this.recordedAt,

    this.receivedAt,

    this.source,

    this.sourceDeviceId,

    this.freshness,

    this.quality,

    this.systolic,

    this.diastolic,

    this.monitoringAvailable,

    this.signalAvailable,

  });



  factory VitalReadingDto.fromJson(Map<String, dynamic>? json) {

    if (json == null) return const VitalReadingDto();

    return VitalReadingDto(

      value: json['value'],

      unit: json['unit']?.toString(),

      recordedAt: json['recorded_at']?.toString(),

      receivedAt: json['received_at']?.toString(),

      source: json['source']?.toString(),

      sourceDeviceId: json['source_device_id']?.toString(),

      freshness: json['freshness']?.toString(),

      quality: json['quality']?.toString(),

      systolic: json['systolic'] is int ? json['systolic'] as int : int.tryParse('${json['systolic']}'),

      diastolic: json['diastolic'] is int ? json['diastolic'] as int : int.tryParse('${json['diastolic']}'),

      monitoringAvailable: json['monitoring_available'] == true,

      signalAvailable: json['signal_available'] == true,

    );

  }



  String? get displayValue {

    if (systolic != null && diastolic != null) {

      return '$systolic/$diastolic';

    }

    if (value == null) return null;

    return value.toString();

  }

}



class VitalsSummaryDto {

  final List<String> sources;

  final String? monitoringState;

  final String? hubStatus;

  final Map<String, VitalReadingDto> vitals;

  final Map<String, dynamic>? legacyHealth;

  final Map<String, dynamic>? deviceEvent;



  const VitalsSummaryDto({

    this.sources = const [],

    this.monitoringState,

    this.hubStatus,

    this.vitals = const {},

    this.legacyHealth,

    this.deviceEvent,

  });



  factory VitalsSummaryDto.fromJson(Map<String, dynamic>? json) {

    if (json == null) return const VitalsSummaryDto();

    final v1 = json['vitals_v1'];

    final vitalsMap = <String, VitalReadingDto>{};

    String? monitoring;

    String? hub;

    if (v1 is Map<String, dynamic>) {

      monitoring = v1['monitoring_state']?.toString();

      hub = v1['hub_status']?.toString();

      final vitalsRaw = v1['vitals'];

      if (vitalsRaw is Map) {

        vitalsRaw.forEach((key, val) {

          if (val is Map<String, dynamic>) {

            vitalsMap[key.toString()] = VitalReadingDto.fromJson(val);

          }

        });

      }

    }

    return VitalsSummaryDto(

      sources: (json['sources'] as List?)?.map((e) => e.toString()).toList() ?? [],

      monitoringState: monitoring,

      hubStatus: hub,

      vitals: vitalsMap,

      legacyHealth: json['legacy_health'] is Map<String, dynamic>

          ? json['legacy_health'] as Map<String, dynamic>

          : null,

      deviceEvent: json['device_event'] is Map<String, dynamic>

          ? json['device_event'] as Map<String, dynamic>

          : null,

    );

  }

}
