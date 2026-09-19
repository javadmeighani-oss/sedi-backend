import 'otp_request.dart';

class OtpVerifyDto {
  final String phone;
  final String code;
  final OtpPurpose purpose;

  const OtpVerifyDto({
    required this.phone,
    required this.code,
    required this.purpose,
  });

  Map<String, dynamic> toJson() {
    return {
      'phone': phone,
      'code': code,
      'purpose': purpose.wireValue,
    };
  }
}
