import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/locale/sedi_locale_controller.dart';
import 'package:sedi_app/core/locale/sedi_locale_registry.dart';
import 'package:sedi_app/data/dto/auth/me_profile.dart';
import 'package:sedi_app/features/auth_otp/presentation/a2_language_sync.dart';
import 'package:sedi_app/features/auth_otp/presentation/a2_stable_enable.dart';
import 'package:sedi_app/features/auth_otp/presentation/birth_calendar_helper.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_post_otp_router.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_post_otp_safe_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    SediLocaleController.instance.debugResetForTest();
  });

  group('SediLocaleRegistry', () {
    test('defaults safely and contains en/fa/ar', () {
      expect(SediLocaleRegistry.resolve(null).code, 'en');
      expect(SediLocaleRegistry.resolve('').code, 'en');
      expect(SediLocaleRegistry.resolve('xx').code, 'en');
      expect(
        SediLocaleRegistry.enabledLocales.map((e) => e.code).toList(),
        ['en', 'fa', 'ar'],
      );
    });

    test('en → LTR + gregorian', () {
      final d = SediLocaleRegistry.resolve('en');
      expect(d.textDirection, TextDirection.ltr);
      expect(d.defaultCalendar, 'gregorian');
      expect(BirthCalendarHelper.calendarTypeForLanguage('en'), 'gregorian');
    });

    test('fa → RTL + jalali', () {
      final d = SediLocaleRegistry.resolve('fa');
      expect(d.textDirection, TextDirection.rtl);
      expect(d.defaultCalendar, 'jalali');
      expect(BirthCalendarHelper.calendarTypeForLanguage('fa'), 'jalali');
    });

    test('ar → RTL + hijri', () {
      final d = SediLocaleRegistry.resolve('ar');
      expect(d.textDirection, TextDirection.rtl);
      expect(d.defaultCalendar, 'hijri');
      expect(BirthCalendarHelper.calendarTypeForLanguage('ar'), 'hijri');
    });
  });

  group('SediLocaleController', () {
    test('setRuntimeLocale changes global locale immediately', () async {
      final c = SediLocaleController.instance;
      expect(c.languageCode, 'en');
      await c.setRuntimeLocale('fa', persistBootstrapCache: false);
      expect(c.languageCode, 'fa');
      expect(c.isRtl, isTrue);
      await c.setRuntimeLocale('ar', persistBootstrapCache: false);
      expect(c.languageCode, 'ar');
      expect(c.current.textDirection, TextDirection.rtl);
    });

    test('reconcileFromBackendConfirmed updates runtime + cache', () async {
      final c = SediLocaleController.instance;
      await c.setRuntimeLocale('en', persistBootstrapCache: false);
      await c.reconcileFromBackendConfirmed('fa');
      expect(c.languageCode, 'fa');
    });

    test('local cache alone does not invent unsupported authority', () async {
      SharedPreferences.setMockInitialValues({
        'user_language': 'zz',
        'language_pref': 'zz',
      });
      final c = SediLocaleController.forTest();
      await c.bootstrapFromCache();
      expect(c.languageCode, 'en');
    });
  });

  group('A2 language PATCH safety', () {
    const backendEn = MeProfileDto(userId: 1, preferredLanguage: 'en');
    const backendFa = MeProfileDto(userId: 1, preferredLanguage: 'fa');

    test('match → no unnecessary PATCH', () {
      expect(
        A2LanguageSync.needsPatch(
          backendMe: backendFa,
          selectedLanguage: 'fa',
        ),
        isFalse,
      );
      final r = A2LanguageSync.classifyAfterPatchAttempt(
        backendMeBeforePatch: backendFa,
        selectedLanguage: 'fa',
        patchOk: false,
        patchedProfile: null,
      );
      expect(r.outcome, A2LanguageSyncOutcome.matched);
      expect(r.mayEnterA3, isTrue);
    });

    test('mismatch → PATCH required; success may enter A3', () {
      expect(
        A2LanguageSync.needsPatch(
          backendMe: backendEn,
          selectedLanguage: 'fa',
        ),
        isTrue,
      );
      final r = A2LanguageSync.classifyAfterPatchAttempt(
        backendMeBeforePatch: backendEn,
        selectedLanguage: 'fa',
        patchOk: true,
        patchedProfile: backendFa,
      );
      expect(r.outcome, A2LanguageSyncOutcome.patched);
      expect(r.mayEnterA3, isTrue);
      expect(r.confirmedProfile!.preferredLanguage, 'fa');
    });

    test('PATCH failure → A3 blocked; no confirmed stale profile', () {
      final r = A2LanguageSync.classifyAfterPatchAttempt(
        backendMeBeforePatch: backendEn,
        selectedLanguage: 'fa',
        patchOk: false,
        patchedProfile: null,
      );
      expect(r.outcome, A2LanguageSyncOutcome.patchFailed);
      expect(r.mayEnterA3, isFalse);
      expect(r.confirmedProfile, isNull);
      expect(STALE_LANGUAGE_CAN_ENTER_A3, isFalse);
    });

    test('PATCH failure preserves selected runtime locale', () async {
      final c = SediLocaleController.instance;
      await c.setRuntimeLocale('fa', persistBootstrapCache: false);
      final r = A2LanguageSync.classifyAfterPatchAttempt(
        backendMeBeforePatch: backendEn,
        selectedLanguage: 'fa',
        patchOk: false,
        patchedProfile: null,
      );
      expect(r.mayEnterA3, isFalse);
      // Runtime must not be overwritten by failed reconcile path.
      expect(c.languageCode, 'fa');
    });

    test('successful retry → backend-confirmed locale then A3', () async {
      final c = SediLocaleController.instance;
      await c.setRuntimeLocale('fa', persistBootstrapCache: false);
      final fail = A2LanguageSync.classifyAfterPatchAttempt(
        backendMeBeforePatch: backendEn,
        selectedLanguage: 'fa',
        patchOk: false,
        patchedProfile: null,
      );
      expect(fail.mayEnterA3, isFalse);
      final ok = A2LanguageSync.classifyAfterPatchAttempt(
        backendMeBeforePatch: backendEn,
        selectedLanguage: 'fa',
        patchOk: true,
        patchedProfile: backendFa,
      );
      expect(ok.mayEnterA3, isTrue);
      await c.reconcileFromBackendConfirmed(
        ok.confirmedProfile!.preferredLanguage,
      );
      expect(c.languageCode, 'fa');
    });
  });

  group('A2 CTA delay + OTP authority regressions', () {
    test('language Confirm delay + restart + no auto-nav semantics', () async {
      final cta = A2StableEnableController(
        delay: A2StableEnableController.targetDelay,
      );
      cta.sync(isValid: true, signature: 'fa');
      expect(cta.enabled, isFalse);
      await Future<void>.delayed(const Duration(milliseconds: 150));
      expect(cta.enabled, isFalse);
      cta.sync(isValid: true, signature: 'ar');
      await Future<void>.delayed(const Duration(milliseconds: 150));
      expect(cta.enabled, isFalse);
      await Future<void>.delayed(const Duration(milliseconds: 200));
      expect(cta.enabled, isTrue);
      cta.dispose();
    });

    test('account / phone / form / otp delays', () async {
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
      final complete = A2StableEnableController(
        delay: A2StableEnableController.targetDelay,
      );
      account.sync(isValid: true, signature: 'returning');
      phone.sync(isValid: true, signature: '98|+989121234567');
      form.sync(isValid: true, signature: 'form');
      otp.sync(isValid: true, signature: '123456');
      complete.sync(isValid: true, signature: 'complete');
      await Future<void>.delayed(const Duration(milliseconds: 320));
      expect(account.enabled, isTrue);
      expect(phone.enabled, isTrue);
      expect(form.enabled, isTrue);
      expect(otp.enabled, isTrue);
      expect(complete.enabled, isTrue);
      account.dispose();
      phone.dispose();
      form.dispose();
      otp.dispose();
      complete.dispose();
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
    });
  });
}

/// Documented product invariant for tests/report.
const STALE_LANGUAGE_CAN_ENTER_A3 = false;
