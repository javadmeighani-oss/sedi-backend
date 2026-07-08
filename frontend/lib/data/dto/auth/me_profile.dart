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
    final rawUserId = json['user_id'] ?? json['id'];
    final userId = _asInt(rawUserId) ?? 0;
    return MeProfileDto(
      userId: userId,
      phone: _asString(json['phone']),
      name: _asString(json['name']) ?? _asString(json['display_name']),
      preferredLanguage: _asString(json['preferred_language']) ??
          _asString(json['language']),
      sex: _asString(json['sex']),
      calendarType: _asString(json['calendar_type']),
      birthDay: _asInt(json['birth_day']),
      birthMonth: _asInt(json['birth_month']),
      birthYear: _asInt(json['birth_year']),
      dateOfBirth: _asDateString(json['date_of_birth']),
    );
  }

  static String? _asString(dynamic value) {
    if (value == null) return null;
    final text = value.toString().trim();
    return text.isEmpty ? null : text;
  }

  static String? _asDateString(dynamic value) {
    if (value == null) return null;
    if (value is String) return value;
    return value.toString();
  }

  static int? _asInt(dynamic value) {
    if (value == null) return null;
    if (value is int) return value;
    if (value is double) return value.round();
    return int.tryParse(value.toString());
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
