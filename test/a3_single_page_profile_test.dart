import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:sedi_app/core/locale/sedi_locale_controller.dart';
import 'package:sedi_app/data/dto/auth/me_profile.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/gate3_localization.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/pages/gate3_profile_page.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/gate3_main_icon_row.dart';

void main() {
  test('1 profile has exactly 3 section titles', () {
    final en = Gate3Localization('en');
    final sections = [
      en.userInformationSection,
      en.userSummarySection,
      en.logoutSection,
    ];
    expect(sections.toSet().length, 3);
    expect(sections.any((s) => s.toLowerCase().contains('what sedi')), isFalse);
  });

  test('2/3 /auth/me field labels include preferred language', () {
    final l10n = Gate3Localization('en');
    expect(l10n.profileNameLabel, isNotEmpty);
    expect(l10n.profileDobLabel, isNotEmpty);
    expect(l10n.profileSexLabel, isNotEmpty);
    expect(l10n.profileLanguageLabel.toLowerCase(), contains('language'));
    expect(l10n.profilePhoneLabel, isNotEmpty);
  });

  test('4 phone OTP strings preserved', () {
    final l10n = Gate3Localization('en');
    expect(l10n.changePhone, isNotEmpty);
    expect(l10n.sendPhoneOtp, isNotEmpty);
    expect(l10n.verifyPhoneOtp, isNotEmpty);
    expect(l10n.phoneChangeSuccess, isNotEmpty);
  });

  test('5 I7 known-facts absent from profile page source', () {
    final src = File(
      'lib/features/gate3_interactive/presentation/pages/gate3_profile_page.dart',
    ).readAsStringSync();
    expect(src.contains('/user/me/known-facts'), isFalse);
    expect(src.contains('whatSediKnows'), isFalse);
    expect(src.contains('profile-summary'), isTrue);
    expect(src.contains('AuthHelper.performLogout'), isTrue);
  });

  test('6 summary table maps backend projection keys/status', () {
    final l10n = Gate3Localization('en');
    expect(l10n.summaryRowLabel('memory_consent'), isNotEmpty);
    expect(l10n.summaryStatusLabel('granted'), isNotEmpty);
    expect(l10n.summaryStatusLabel('in_progress'), isNotEmpty);
  });

  test('7 no technical IDs / Sedi ID / I9 in profile l10n surface', () {
    final l10n = Gate3Localization('en');
    final blob = [
      l10n.profileTitle,
      l10n.userInformationSection,
      l10n.userSummarySection,
      l10n.logoutSection,
      l10n.summaryRowLabel('daily_plan'),
    ].join(' ').toLowerCase();
    expect(blob.contains('sedi id'), isFalse);
    expect(blob.contains('health_subject'), isFalse);
    expect(blob.contains('heart-rate'), isFalse);
    expect(blob.contains('unstable'), isFalse);
  });

  testWidgets('8/9 logout at bottom contract + direct profile navigation',
      (tester) async {
    final src = File(
      'lib/features/gate3_interactive/presentation/pages/gate3_profile_page.dart',
    ).readAsStringSync();
    final logoutIdx = src.indexOf('AuthHelper.performLogout');
    final summaryIdx = src.indexOf('userSummarySection');
    expect(logoutIdx, greaterThan(summaryIdx));

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Gate3MainIconRow(
            onHealthCare: () {},
            onLifestyle: () {},
            onGadgets: () {},
            lang: 'en',
          ),
        ),
      ),
    );
    expect(find.byIcon(Icons.settings_outlined), findsOneWidget);
    await tester.tap(find.byIcon(Icons.settings_outlined));
    // Do not pumpAndSettle — Profile _load hits network and would hang.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.byType(Gate3ProfilePage), findsOneWidget);
  });

  test('10 en/fa/ar + RTL/LTR', () {
    expect(Gate3Localization('en').isRtl, isFalse);
    expect(Gate3Localization('fa').isRtl, isTrue);
    expect(Gate3Localization('ar').isRtl, isTrue);
    expect(Gate3Localization('fa').userInformationSection, isNotEmpty);
    expect(Gate3Localization('ar').userSummarySection, isNotEmpty);
    expect(Gate3Localization('en').logout, isNotEmpty);
  });

  test('MeProfileDto preferred_language parse regression', () {
    final me = MeProfileDto.fromJson({
      'user_id': 1,
      'name': 'Ada',
      'preferred_language': 'fa',
      'phone': '+15551212',
      'sex': 'female',
    });
    expect(me.preferredLanguage, 'fa');
    expect(me.name, 'Ada');
    SediLocaleController.instance.reconcileFromBackendConfirmed('fa');
    expect(SediLocaleController.instance.languageCode, 'fa');
  });
}
