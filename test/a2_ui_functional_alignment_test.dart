import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/data/dto/auth/me_profile.dart';
import 'package:sedi_app/features/auth_otp/presentation/a2_language_sync.dart';
import 'package:sedi_app/features/auth_otp/presentation/a2_otp_error_mapper.dart';
import 'package:sedi_app/features/auth_otp/presentation/a2_stable_enable.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_otp_input.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_post_otp_router.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_post_otp_safe_router.dart';
import 'package:sedi_app/features/auth_otp/presentation/otp_login_localization.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('A2 language immediate UI + direction', () {
    testWidgets('selecting fa immediately gives Persian + RTL', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: _LanguageProbe(initial: null),
        ),
      );
      await tester.tap(find.text('فارسی'));
      await tester.pump();
      final dir = tester.widget<Directionality>(find.byType(Directionality).last);
      expect(dir.textDirection, TextDirection.rtl);
      expect(find.text('تأیید'), findsOneWidget);
      expect(find.text('Confirm'), findsNothing);
    });

    testWidgets('selecting ar immediately gives Arabic + RTL', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: _LanguageProbe(initial: null),
        ),
      );
      await tester.tap(find.text('العربية'));
      await tester.pump();
      final dir = tester.widget<Directionality>(find.byType(Directionality).last);
      expect(dir.textDirection, TextDirection.rtl);
      expect(find.text('تأكيد'), findsOneWidget);
    });

    testWidgets('selecting en gives English + LTR', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: _LanguageProbe(initial: null),
        ),
      );
      await tester.tap(find.text('English'));
      await tester.pump();
      final dir = tester.widget<Directionality>(find.byType(Directionality).last);
      expect(dir.textDirection, TextDirection.ltr);
      expect(find.text('Confirm'), findsOneWidget);
    });

    testWidgets('Confirm disabled before selection and during 300ms',
        (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: _LanguageProbe(initial: null),
        ),
      );
      final before = tester.widget<ElevatedButton>(find.byType(ElevatedButton));
      expect(before.onPressed, isNull);

      await tester.tap(find.text('English'));
      await tester.pump();
      final during = tester.widget<ElevatedButton>(find.byType(ElevatedButton));
      expect(during.onPressed, isNull);

      await tester.pump(const Duration(milliseconds: 320));
      final after = tester.widget<ElevatedButton>(find.byType(ElevatedButton));
      expect(after.onPressed, isNotNull);
    });

    testWidgets('no auto-navigation after language selection', (tester) async {
      var advanced = false;
      await tester.pumpWidget(
        MaterialApp(
          home: _LanguageProbe(
            initial: null,
            onConfirm: () => advanced = true,
          ),
        ),
      );
      await tester.tap(find.text('فارسی'));
      await tester.pump(const Duration(milliseconds: 320));
      expect(advanced, isFalse);
      await tester.tap(find.byType(ElevatedButton));
      await tester.pump();
      expect(advanced, isTrue);
    });
  });

  group('A2 language backend sync', () {
    test('selected language syncs via PATCH when backend differs', () {
      const me = MeProfileDto(userId: 1, preferredLanguage: 'en');
      expect(
        A2LanguageSync.needsPatch(backendMe: me, selectedLanguage: 'fa'),
        isTrue,
      );
      final dto = A2LanguageSync.patchDto('fa');
      expect(dto.toJson()['preferred_language'], 'fa');
    });

    test('no PATCH when preferred_language already matches', () {
      const me = MeProfileDto(userId: 1, preferredLanguage: 'fa');
      expect(
        A2LanguageSync.needsPatch(backendMe: me, selectedLanguage: 'fa'),
        isFalse,
      );
    });
  });

  group('A2 OTP error code mapping', () {
    test('OTP_INVALID / OTP_EXPIRED / TOO_MANY_ATTEMPTS / OTP_REQUEST_FAILED',
        () {
      const fa = OtpLoginLocalization('fa');
      expect(
        A2OtpErrorMapper.mapVerify(l10n: fa, code: 'OTP_INVALID'),
        fa.otpInvalid,
      );
      expect(
        A2OtpErrorMapper.mapVerify(l10n: fa, code: 'OTP_EXPIRED'),
        fa.otpExpired,
      );
      expect(
        A2OtpErrorMapper.mapVerify(l10n: fa, code: 'TOO_MANY_ATTEMPTS'),
        fa.tooManyOtp,
      );
      expect(
        A2OtpErrorMapper.mapRequest(l10n: fa, code: 'OTP_REQUEST_FAILED'),
        fa.genericOtpRequestFailed,
      );

      const en = OtpLoginLocalization('en');
      expect(
        A2OtpErrorMapper.mapVerify(l10n: en, code: 'OTP_INVALID'),
        en.otpInvalid,
      );
      const ar = OtpLoginLocalization('ar');
      expect(
        A2OtpErrorMapper.mapVerify(l10n: ar, code: 'OTP_EXPIRED'),
        ar.otpExpired,
      );
    });
  });

  group('A2 OTP no auto-submit + authority', () {
    test('six-digit complete does not imply verify action (helper only)', () {
      expect(OtpInputHelper.isComplete('123456'), isTrue);
      // Verify requires explicit CTA; StableEnable starts disabled.
      final c = A2StableEnableController(
        delay: A2StableEnableController.targetDelay,
      );
      c.sync(isValid: true, signature: '123456');
      expect(c.enabled, isFalse);
      c.dispose();
    });

    test('OTP fallback cannot enter A3', () {
      const me = MeProfileDto(
        userId: 7,
        phone: '+989121234567',
        name: 'Ali',
        sex: 'male',
        preferredLanguage: 'fa',
        calendarType: 'jalali',
        birthDay: 1,
        birthMonth: 1,
        birthYear: 1370,
        dateOfBirth: '1991-03-21',
      );
      final action = Gate2PostOtpSafeRouter.resolve(
        meSource: PostOtpMeSource.otpFallbackDraft,
        isNewUserPath: false,
        me: me,
        registrationDraftComplete: true,
      );
      expect(action, isNot(Gate2PostOtpAction.enterGate3));
      expect(
        Gate2PostOtpSafeRouter.requiresBackendConfirmedProfile(
          Gate2PostOtpAction.enterGate3,
        ),
        isTrue,
      );
    });

    test('backend-confirmed profile required before A3', () {
      const me = MeProfileDto(
        userId: 7,
        phone: '+989121234567',
        name: 'Ali',
        sex: 'male',
        preferredLanguage: 'en',
        calendarType: 'gregorian',
        birthDay: 1,
        birthMonth: 1,
        birthYear: 1990,
        dateOfBirth: '1990-01-01',
      );
      final backend = Gate2PostOtpSafeRouter.resolve(
        meSource: PostOtpMeSource.backendConfirmed,
        isNewUserPath: false,
        me: me,
        registrationDraftComplete: true,
      );
      expect(backend, Gate2PostOtpAction.enterGate3);
    });
  });
}

/// Minimal A2 language-step probe matching production behavior:
/// immediate l10n + direction on select; Confirm gated by 300ms stable enable.
class _LanguageProbe extends StatefulWidget {
  final String? initial;
  final VoidCallback? onConfirm;

  const _LanguageProbe({
    this.initial,
    this.onConfirm,
  });

  @override
  State<_LanguageProbe> createState() => _LanguageProbeState();
}

class _LanguageProbeState extends State<_LanguageProbe> {
  String? _language;
  final _cta = A2StableEnableController(
    delay: A2StableEnableController.targetDelay,
  );

  @override
  void initState() {
    super.initState();
    _language = widget.initial;
    _cta.addListener(() {
      if (mounted) setState(() {});
    });
    _cta.sync(isValid: _language != null, signature: _language);
  }

  @override
  void dispose() {
    _cta.dispose();
    super.dispose();
  }

  OtpLoginLocalization get _l10n => OtpLoginLocalization(_language ?? 'en');

  @override
  Widget build(BuildContext context) {
    final direction =
        _language == null ? TextDirection.ltr : _l10n.textDirection;
    return Directionality(
      textDirection: direction,
      child: Scaffold(
        body: Column(
          children: [
            TextButton(
              onPressed: () => setState(() {
                _language = 'ar';
                _cta.sync(isValid: true, signature: _language);
              }),
              child: const Text('العربية'),
            ),
            TextButton(
              onPressed: () => setState(() {
                _language = 'en';
                _cta.sync(isValid: true, signature: _language);
              }),
              child: const Text('English'),
            ),
            TextButton(
              onPressed: () => setState(() {
                _language = 'fa';
                _cta.sync(isValid: true, signature: _language);
              }),
              child: const Text('فارسی'),
            ),
            ElevatedButton(
              onPressed: _cta.enabled ? widget.onConfirm ?? () {} : null,
              child: Text(_l10n.confirm),
            ),
          ],
        ),
      ),
    );
  }
}

extension on OtpLoginLocalization {
  TextDirection get textDirection =>
      isRtl ? TextDirection.rtl : TextDirection.ltr;
}
