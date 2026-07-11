class CaregiverDto {

  final int id;

  final String name;

  final String? phone;

  final String? relationship;

  final int priority;

  final bool notifyDailyStatus;

  final bool notifyEmergency;

  final bool notifyCareSummary;

  final bool notifyVitalAlerts;

  final int? emergencyPriority;

  final bool isActive;



  const CaregiverDto({

    required this.id,

    required this.name,

    this.phone,

    this.relationship,

    this.priority = 0,

    this.notifyDailyStatus = false,

    this.notifyEmergency = true,

    this.notifyCareSummary = false,

    this.notifyVitalAlerts = false,

    this.emergencyPriority,

    this.isActive = true,

  });



  factory CaregiverDto.fromJson(Map<String, dynamic> json) {

    return CaregiverDto(

      id: json['id'] is int ? json['id'] as int : int.parse('${json['id']}'),

      name: json['name']?.toString() ?? '',

      phone: json['phone']?.toString(),

      relationship: json['relationship']?.toString(),

      priority: json['priority'] is int

          ? json['priority'] as int

          : int.tryParse('${json['priority']}') ?? 0,

      notifyDailyStatus: json['notify_daily_status'] == true,

      notifyEmergency: json['notify_emergency'] != false,

      notifyCareSummary: json['notify_care_summary'] == true,

      notifyVitalAlerts: json['notify_vital_alerts'] == true,

      emergencyPriority: json['emergency_priority'] is int

          ? json['emergency_priority'] as int

          : int.tryParse('${json['emergency_priority']}'),

      isActive: json['is_active'] != false,

    );

  }



  Map<String, dynamic> toCreateJson({

    required String name,

    String? phone,

    String? relationship,

    bool notifyDailyStatus = false,

    bool notifyEmergency = true,

    bool notifyCareSummary = false,

    bool notifyVitalAlerts = false,

    int? emergencyPriority,

  }) {

    return {

      'name': name,

      if (phone != null && phone.isNotEmpty) 'phone': phone,

      if (relationship != null && relationship.isNotEmpty)

        'relationship': relationship,

      'notify_daily_status': notifyDailyStatus,

      'notify_emergency': notifyEmergency,

      'notify_care_summary': notifyCareSummary,

      'notify_vital_alerts': notifyVitalAlerts,

      if (emergencyPriority != null) 'emergency_priority': emergencyPriority,

    };

  }



  Map<String, dynamic> toUpdateJson({

    String? name,

    String? phone,

    String? relationship,

    bool? notifyDailyStatus,

    bool? notifyEmergency,

    bool? notifyCareSummary,

    bool? notifyVitalAlerts,

    int? emergencyPriority,

  }) {

    final map = <String, dynamic>{};

    if (name != null) map['name'] = name;

    if (phone != null) map['phone'] = phone;

    if (relationship != null) map['relationship'] = relationship;

    if (notifyDailyStatus != null) {

      map['notify_daily_status'] = notifyDailyStatus;

    }

    if (notifyEmergency != null) map['notify_emergency'] = notifyEmergency;

    if (notifyCareSummary != null) {

      map['notify_care_summary'] = notifyCareSummary;

    }

    if (notifyVitalAlerts != null) {

      map['notify_vital_alerts'] = notifyVitalAlerts;

    }

    if (emergencyPriority != null) {

      map['emergency_priority'] = emergencyPriority;

    }

    return map;

  }

}
