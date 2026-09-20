import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_otp_input.dart';

void main() {
  group('OtpInputHelper', () {
    test('sanitize ASCII digits and limits to six', () {
      expect(OtpInputHelper.sanitize('12a34b56c78'), '123456');
      expect(OtpInputHelper.sanitize('1234567890'), '123456');
    });

    test('sanitize Persian digits to ASCII', () {
      expect(OtpInputHelper.sanitize('۱۲۳۴۵۶'), '123456');
      expect(OtpInputHelper.sanitize('۱۲۳۴۵۶۷۸'), '123456');
    });

    test('sanitize Arabic-Indic digits to ASCII', () {
      expect(OtpInputHelper.sanitize('١٢٣٤٥٦'), '123456');
    });

    test('sanitize mixed ASCII/Persian/Arabic-Indic', () {
      expect(OtpInputHelper.sanitize('12۳٤5۶'), '123456');
    });

    test('rejects non-digits', () {
      expect(OtpInputHelper.sanitize('12-34*56'), '123456');
      expect(OtpInputHelper.sanitize('abc'), '');
    });

    test('isComplete is true only for six ASCII digits after normalize', () {
      expect(OtpInputHelper.isComplete('12345'), isFalse);
      expect(OtpInputHelper.isComplete('123456'), isTrue);
      expect(OtpInputHelper.isComplete('۱۲۳۴۵۶'), isTrue);
      expect(OtpInputHelper.isComplete('12 34 56'), isTrue);
    });

    test('digitAt returns ASCII characters', () {
      expect(OtpInputHelper.digitAt('۱۲۴۵۶۱', 0), '1');
      expect(OtpInputHelper.digitAt('۱۲۴۵۶۱', 5), '1');
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

  group('OtpDigitInputFormatter', () {
    final formatter = OtpDigitInputFormatter();

    TextEditingValue apply(String text) {
      return formatter.formatEditUpdate(
        TextEditingValue.empty,
        TextEditingValue(
          text: text,
          selection: TextSelection.collapsed(offset: text.length),
        ),
      );
    }

    test('formatter normalizes Persian and caps length', () {
      final v = apply('۱۲۳۴۵۶۷');
      expect(v.text, '123456');
      expect(v.selection.baseOffset, 6);
    });

    test('formatter normalizes Arabic-Indic', () {
      expect(apply('١٢٣٤٥٦').text, '123456');
    });

    test('formatter keeps ASCII sequential typing', () {
      expect(apply('1').text, '1');
      expect(apply('12').text, '12');
      expect(apply('123456').text, '123456');
    });
  });
}
