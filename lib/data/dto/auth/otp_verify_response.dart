class OtpVerifyResponse {
  final int? userId;
  final String? phone;
  final String? accessToken;
  final String? refreshToken;
  final String? tokenType;
  final int? expiresIn;
  final String? language;
  final String? name;
  final String? sex;
  final String? dateOfBirth;

  const OtpVerifyResponse({
    this.userId,
    this.phone,
    this.accessToken,
    this.refreshToken,
    this.tokenType,
    this.expiresIn,
    this.language,
    this.name,
    this.sex,
    this.dateOfBirth,
  });

  factory OtpVerifyResponse.fromJson(Map<String, dynamic> json) {
    final rawUserId = json['user_id'];
    return OtpVerifyResponse(
      userId: rawUserId is int
          ? rawUserId
          : int.tryParse(rawUserId?.toString() ?? ''),
      phone: json['phone']?.toString(),
      accessToken: json['access_token']?.toString(),
      refreshToken: json['refresh_token']?.toString(),
      tokenType: json['token_type']?.toString(),
      expiresIn: json['expires_in'] is int
          ? json['expires_in'] as int
          : int.tryParse(json['expires_in']?.toString() ?? ''),
      language: json['language']?.toString(),
      name: json['name']?.toString(),
      sex: json['sex']?.toString(),
      dateOfBirth: json['date_of_birth']?.toString(),
    );
  }

  OtpVerifyResponse copyWith({
    int? userId,
    String? phone,
    String? accessToken,
    String? refreshToken,
    String? tokenType,
    int? expiresIn,
    String? language,
    String? name,
    String? sex,
    String? dateOfBirth,
  }) {
    return OtpVerifyResponse(
      userId: userId ?? this.userId,
      phone: phone ?? this.phone,
      accessToken: accessToken ?? this.accessToken,
      refreshToken: refreshToken ?? this.refreshToken,
      tokenType: tokenType ?? this.tokenType,
      expiresIn: expiresIn ?? this.expiresIn,
      language: language ?? this.language,
      name: name ?? this.name,
      sex: sex ?? this.sex,
      dateOfBirth: dateOfBirth ?? this.dateOfBirth,
    );
  }
}
