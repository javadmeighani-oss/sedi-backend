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

  group('OtpInputHelper.applyEdit selection-aware', () {
    TextEditingValue edit({
      required String oldText,
      required String newText,
      required TextSelection oldSel,
      TextSelection? newSel,
    }) {
      return OtpInputHelper.applyEdit(
        oldValue: TextEditingValue(text: oldText, selection: oldSel),
        newValue: TextEditingValue(
          text: newText,
          selection: newSel ?? TextSelection.collapsed(offset: newText.length),
        ),
      );
    }

    test('replace only the selected filled digit', () {
      final v = edit(
        oldText: '123456',
        newText: '129456',
        oldSel: const TextSelection(baseOffset: 2, extentOffset: 3),
      );
      expect(v.text, '129456');
      expect(OtpInputHelper.isComplete(v.text), isTrue);
    });

    test('delete middle digit then retype inserts at collapsed caret', () {
      final afterDelete = edit(
        oldText: '123456',
        newText: '12456',
        oldSel: const TextSelection(baseOffset: 2, extentOffset: 3),
      );
      expect(afterDelete.text, '12456');
      expect(afterDelete.selection.isCollapsed, isTrue);
      expect(afterDelete.selection.extentOffset, 2);

      final afterType = OtpInputHelper.applyEdit(
        oldValue: afterDelete,
        newValue: const TextEditingValue(
          text: '129456',
          selection: TextSelection.collapsed(offset: 3),
        ),
      );
      expect(afterType.text, '129456');
      expect(afterType.text, isNot('19456'));
      expect(afterType.text, isNot('12956'));
    });

    test('empty next slot appends without changing earlier digits', () {
      final v = edit(
        oldText: '12',
        newText: '123',
        oldSel: const TextSelection.collapsed(offset: 2),
      );
      expect(v.text, '123');
    });

    test('backspace on selected digit shifts later digits and keeps prefix', () {
      final v = edit(
        oldText: '123456',
        newText: '12456',
        oldSel: const TextSelection(baseOffset: 2, extentOffset: 3),
      );
      expect(v.text, '12456');
    });

    test('backspace at end deletes last digit only', () {
      final v = edit(
        oldText: '123',
        newText: '12',
        oldSel: const TextSelection.collapsed(offset: 3),
      );
      expect(v.text, '12');
    });

    test('empty + paste 654321 replaces entire OTP', () {
      final v = edit(
        oldText: '',
        newText: '654321',
        oldSel: const TextSelection.collapsed(offset: 0),
      );
      expect(v.text, '654321');
      expect(v.selection.isCollapsed, isTrue);
      expect(v.selection.extentOffset, 6);
    });

    test('partial 12 + paste 654321 replaces entire OTP', () {
      final v = edit(
        oldText: '12',
        newText: '12654321',
        oldSel: const TextSelection.collapsed(offset: 2),
      );
      expect(v.text, '654321');
    });

    test('full 123456 + middle slot + paste 654321 replaces entire OTP', () {
      final spliced = edit(
        oldText: '123456',
        newText: '12654321456',
        oldSel: const TextSelection(baseOffset: 2, extentOffset: 3),
      );
      expect(spliced.text, '654321');
      expect(spliced.text, isNot('126543'));

      final wholesale = edit(
        oldText: '123456',
        newText: '654321',
        oldSel: const TextSelection(baseOffset: 2, extentOffset: 3),
      );
      expect(wholesale.text, '654321');
    });

    test('six-digit paste/autofill fills all boxes', () {
      final v = edit(
        oldText: '',
        newText: '12۳٤5۶',
        oldSel: const TextSelection.collapsed(offset: 0),
      );
      expect(v.text, '123456');
      expect(OtpInputHelper.isComplete(v.text), isTrue);
    });

    test('Persian/Arabic six-digit paste normalizes and replaces entire OTP', () {
      expect(
        edit(
          oldText: '123456',
          newText: '۶۵۴۳۲۱',
          oldSel: const TextSelection(baseOffset: 2, extentOffset: 3),
        ).text,
        '654321',
      );
      expect(
        edit(
          oldText: '12',
          newText: '٦٥٤٣٢١',
          oldSel: const TextSelection.collapsed(offset: 2),
        ).text,
        '654321',
      );
    });

    test('replaceDigit leaves other slots unchanged', () {
      expect(OtpInputHelper.replaceDigit('123456', 2, '9'), '129456');
      expect(OtpInputHelper.replaceDigit('12', 0, '۸'), '82');
    });

    test('selectionForSlot does not change the code', () {
      const code = '123456';
      final sel = OtpInputHelper.selectionForSlot(code, 3);
      expect(sel.start, 3);
      expect(sel.end, 4);
      expect(OtpInputHelper.sanitize(code), '123456');
    });
  });
}
