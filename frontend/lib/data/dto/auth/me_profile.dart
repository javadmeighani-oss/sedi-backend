class MeProfileDto {
  final int userId;
  final String? phone;
  final String? name;
  final String? preferredLanguage;
  final String? sex;
  final String? calendarType;
  final int? birthDay;
  final int? birthMonth;
  final int? birthYear;
  final String? dateOfBirth;

  const MeProfileDto({
    required this.userId,
    this.phone,
    this.name,
    this.preferredLanguage,
    this.sex,
    this.calendarType,
    this.birthDay,
    this.birthMonth,
    this.birthYear,
    this.dateOfBirth,
  });

  factory MeProfileDto.fromJson(Map<String, dynamic> json) {
    final rawUserId = json['user_id'];
    final userId = rawUserId is int
        ? rawUserId
        : int.tryParse(rawUserId?.toString() ?? '') ?? 0;
    return MeProfileDto(
      userId: userId,
      phone: json['phone']?.toString(),
      name: json['name']?.toString() ?? json['display_name']?.toString(),
      preferredLanguage: json['preferred_language']?.toString() ??
          json['language']?.toString(),
      sex: json['sex']?.toString(),
      calendarType: json['calendar_type']?.toString(),
      birthDay: _asInt(json['birth_day']),
      birthMonth: _asInt(json['birth_month']),
      birthYear: _asInt(json['birth_year']),
      dateOfBirth: json['date_of_birth']?.toString(),
    );
  }

  static int? _asInt(dynamic value) {
    if (value is int) return value;
    return int.tryParse(value?.toString() ?? '');
  }
}

class MeUpdateDto {
  final String? name;
  final String? sex;
  final String? preferredLanguage;
  final String? calendarType;
  final int? birthDay;
  final int? birthMonth;
  final int? birthYear;
  final String? dateOfBirth;

  const MeUpdateDto({
    this.name,
    this.sex,
    this.preferredLanguage,
    this.calendarType,
    this.birthDay,
    this.birthMonth,
    this.birthYear,
    this.dateOfBirth,
  });

  Map<String, dynamic> toJson() {
    return {
      if (name != null) 'name': name,
      if (sex != null) 'sex': sex,
      if (preferredLanguage != null) 'preferred_language': preferredLanguage,
      if (calendarType != null) 'calendar_type': calendarType,
      if (birthDay != null) 'birth_day': birthDay,
      if (birthMonth != null) 'birth_month': birthMonth,
      if (birthYear != null) 'birth_year': birthYear,
      if (dateOfBirth != null) 'date_of_birth': dateOfBirth,
    };
  }
}
