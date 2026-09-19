enum OtpPurpose {
  login('LOGIN'),
  registration('REGISTRATION');

  const OtpPurpose(this.wireValue);

  final String wireValue;
}

class OtpRequestDto {
  final String phone;
  final OtpPurpose purpose;

  const OtpRequestDto({
    required this.phone,
    required this.purpose,
  });

  Map<String, dynamic> toJson() {
    return {
      'phone': phone,
      'purpose': purpose.wireValue,
    };
  }
}
