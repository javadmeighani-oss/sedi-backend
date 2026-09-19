import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_otp_input.dart';

void main() {
  group('OtpInputHelper', () {
    test('sanitize keeps only digits and limits to six', () {
      expect(OtpInputHelper.sanitize('12a34b56c78'), '123456');
      expect(OtpInputHelper.sanitize('1234567890'), '123456');
    });

    test('isComplete is true only for six digits', () {
      expect(OtpInputHelper.isComplete('12345'), isFalse);
      expect(OtpInputHelper.isComplete('123456'), isTrue);
      expect(OtpInputHelper.isComplete('12 34 56'), isTrue);
    });

    test('digitAt returns expected characters', () {
      expect(OtpInputHelper.digitAt('124561', 0), '1');
      expect(OtpInputHelper.digitAt('124561', 5), '1');
      expect(OtpInputHelper.digitAt('12', 3), '');
    });

    test('single update populates all digit positions', () {
      const code = '987654';
      final digits = List<String>.generate(
        OtpInputHelper.codeLength,
        (index) => OtpInputHelper.digitAt(code, index),
      );
      expect(digits, ['9', '8', '7', '6', '5', '4']);
      expect(OtpInputHelper.isComplete(code), isTrue);
    });
  });
}
