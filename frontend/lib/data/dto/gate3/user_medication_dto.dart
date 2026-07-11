class UserMedicationDto {

  final int id;

  final String name;

  final String? userDosage;

  final String? instructions;

  final bool reminderEnabled;

  final List<String> reminderTimes;

  final int intervalHours;

  final String? timezone;

  final double? remainingQuantity;

  final String? quantityUnit;

  final double? refillThreshold;

  final String? stockLevel;



  const UserMedicationDto({

    required this.id,

    required this.name,

    this.userDosage,

    this.instructions,

    this.reminderEnabled = true,

    this.reminderTimes = const [],

    this.intervalHours = 8,

    this.timezone,

    this.remainingQuantity,

    this.quantityUnit,

    this.refillThreshold,

    this.stockLevel,

  });



  factory UserMedicationDto.fromJson(Map<String, dynamic> json) {

    final times = json['reminder_times'];

    return UserMedicationDto(

      id: json['id'] is int ? json['id'] as int : int.parse('${json['id']}'),

      name: json['name']?.toString() ?? '',

      userDosage: json['user_dosage']?.toString(),

      instructions: json['instructions']?.toString(),

      reminderEnabled: json['reminder_enabled'] != false,

      reminderTimes: times is List ? times.map((e) => e.toString()).toList() : [],

      intervalHours: json['interval_hours'] is int

          ? json['interval_hours'] as int

          : int.tryParse('${json['interval_hours']}') ?? 8,

      timezone: json['timezone']?.toString(),

      remainingQuantity: json['remaining_quantity'] is num

          ? (json['remaining_quantity'] as num).toDouble()

          : double.tryParse('${json['remaining_quantity']}'),

      quantityUnit: json['quantity_unit']?.toString(),

      refillThreshold: json['refill_threshold'] is num

          ? (json['refill_threshold'] as num).toDouble()

          : double.tryParse('${json['refill_threshold']}'),

      stockLevel: json['stock_level']?.toString(),

    );

  }



  Map<String, dynamic> toScheduleUpdateJson({

    bool? reminderEnabled,

    List<String>? reminderTimes,

    int? intervalHours,

    String? timezone,

    double? remainingQuantity,

    String? quantityUnit,

    double? refillThreshold,

  }) {

    final map = <String, dynamic>{};

    if (reminderEnabled != null) map['reminder_enabled'] = reminderEnabled;

    if (reminderTimes != null) map['reminder_times'] = reminderTimes;

    if (intervalHours != null) map['interval_hours'] = intervalHours;

    if (timezone != null) map['timezone'] = timezone;

    if (remainingQuantity != null) map['remaining_quantity'] = remainingQuantity;

    if (quantityUnit != null) map['quantity_unit'] = quantityUnit;

    if (refillThreshold != null) map['refill_threshold'] = refillThreshold;

    return map;

  }

}
