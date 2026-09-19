import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/auth_otp/presentation/a2_stable_enable.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('A2StableEnableController', () {
    test('Confirm disabled before valid selection', () {
      final c = A2StableEnableController(
        delay: A2StableEnableController.targetDelay,
      );
      c.sync(isValid: false, signature: null);
      expect(c.enabled, isFalse);
      c.dispose();
    });

    test('remains disabled during 300ms stabilization', () async {
      final c = A2StableEnableController(
        delay: A2StableEnableController.targetDelay,
      );
      c.sync(isValid: true, signature: 'fa');
      expect(c.enabled, isFalse);
      await Future<void>.delayed(const Duration(milliseconds: 150));
      expect(c.enabled, isFalse);
      c.dispose();
    });

    test('enables after 300ms stabilization', () async {
      final c = A2StableEnableController(
        delay: A2StableEnableController.targetDelay,
      );
      var notified = false;
      c.addListener(() => notified = true);
      c.sync(isValid: true, signature: 'en');
      expect(c.enabled, isFalse);
      await Future<void>.delayed(const Duration(milliseconds: 320));
      expect(c.enabled, isTrue);
      expect(notified, isTrue);
      c.dispose();
    });

    test('changing selection restarts delay', () async {
      final c = A2StableEnableController(
        delay: A2StableEnableController.targetDelay,
      );
      c.sync(isValid: true, signature: 'fa');
      await Future<void>.delayed(const Duration(milliseconds: 200));
      expect(c.enabled, isFalse);
      c.sync(isValid: true, signature: 'ar');
      await Future<void>.delayed(const Duration(milliseconds: 200));
      expect(c.enabled, isFalse);
      await Future<void>.delayed(const Duration(milliseconds: 150));
      expect(c.enabled, isTrue);
      c.dispose();
    });

    test('invalid state disables immediately', () async {
      final c = A2StableEnableController(
        delay: A2StableEnableController.targetDelay,
      );
      c.sync(isValid: true, signature: 'phone');
      await Future<void>.delayed(const Duration(milliseconds: 320));
      expect(c.enabled, isTrue);
      final changed = c.sync(isValid: false, signature: null);
      expect(changed, isTrue);
      expect(c.enabled, isFalse);
      c.dispose();
    });

    test('account-choice / phone / form / otp signatures stabilize independently',
        () async {
      final account = A2StableEnableController(
        delay: A2StableEnableController.targetDelay,
      );
      final phone = A2StableEnableController(
        delay: A2StableEnableController.targetDelay,
      );
      final form = A2StableEnableController(
        delay: A2StableEnableController.targetDelay,
      );
      final otp = A2StableEnableController(
        delay: A2StableEnableController.targetDelay,
      );

      account.sync(isValid: true, signature: 'returning');
      phone.sync(isValid: true, signature: '98|+989121234567');
      form.sync(isValid: true, signature: 'Ali|male|1|1|1370|+989121234567');
      otp.sync(isValid: true, signature: '123456');

      expect(account.enabled, isFalse);
      expect(phone.enabled, isFalse);
      expect(form.enabled, isFalse);
      expect(otp.enabled, isFalse);

      await Future<void>.delayed(const Duration(milliseconds: 320));
      expect(account.enabled, isTrue);
      expect(phone.enabled, isTrue);
      expect(form.enabled, isTrue);
      expect(otp.enabled, isTrue);

      account.dispose();
      phone.dispose();
      form.dispose();
      otp.dispose();
    });
  });
}
