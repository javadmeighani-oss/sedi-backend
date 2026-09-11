import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/theme/app_theme.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/gate3_localization.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/gate3_main_icon_row.dart';
import 'package:sedi_app/features/lifestyle/presentation/lifestyle_l10n.dart';
import 'package:sedi_app/features/lifestyle/presentation/pages/lifestyle_health_page.dart';
import 'package:sedi_app/features/lifestyle/presentation/pages/lifestyle_page.dart';

void main() {
  test('1 lifestyle has exactly 5 primary sections', () {
    final l10n = LifestyleL10n('en');
    expect(l10n.sectionTitles.length, 5);
    expect(l10n.sectionTitles.toSet().length, 5);
  });

  test('2/3 health top icon removed; profile/lifestyle/gadgets/notifications present',
      () {
    final src = File(
      'lib/features/gate3_interactive/presentation/widgets/gate3_main_icon_row.dart',
    ).readAsStringSync();
    expect(src.contains('onHealthCare'), isFalse);
    expect(src.contains('healthCare'), isFalse);
    expect(src.contains('onNotifications'), isTrue);
    expect(src.contains('onLifestyle'), isTrue);
    expect(src.contains('onGadgets'), isTrue);
    expect(src.contains('Gate3ProfilePage'), isTrue);
  });

  test('4 AppTheme status tokens exist (no red for I9 change)', () {
    expect(AppTheme.statusStableOlive, isNot(AppTheme.dangerRed));
    expect(AppTheme.statusChangeAmber, isNot(AppTheme.dangerRed));
    expect(AppTheme.statusNeutralMuted, isNot(AppTheme.dangerRed));
  });

  test('5 en/fa/ar + RTL/LTR', () {
    expect(LifestyleL10n('en').isRtl, isFalse);
    expect(LifestyleL10n('fa').isRtl, isTrue);
    expect(LifestyleL10n('ar').isRtl, isTrue);
    expect(LifestyleL10n('fa').health, isNotEmpty);
    expect(LifestyleL10n('ar').mySchedule, isNotEmpty);
  });

  test('6/7/8 I9 status mapping — amber not red for changed', () {
    final l10n = LifestyleL10n('en');
    expect(l10n.hrStatusLabel('STABLE'), contains('Stable'));
    expect(l10n.hrStatusLabel('UNSTABLE_OR_CHANGED'), contains('Change'));
    expect(l10n.hrStatusLabel('INSUFFICIENT_DATA'), contains('Not enough'));
    final healthSrc = File(
      'lib/features/lifestyle/presentation/pages/lifestyle_health_page.dart',
    ).readAsStringSync();
    expect(healthSrc.contains('statusChangeAmber'), isTrue);
    expect(healthSrc.contains('statusStableOlive'), isTrue);
    // I9 changed state must not use dangerRed in status mapping.
    final statusFn = RegExp(
      r'Color _statusColor[\s\S]*?default:\s*return AppTheme\.statusNeutralMuted;',
    ).firstMatch(healthSrc)?.group(0);
    expect(statusFn, isNotNull);
    expect(statusFn!.contains('dangerRed'), isFalse);
    expect(statusFn.contains('UNSTABLE_OR_CHANGED'), isTrue);
  });

  test('9/10 health page uses backend projection + ranges', () {
    final src = File(
      'lib/features/lifestyle/presentation/pages/lifestyle_health_page.dart',
    ).readAsStringSync();
    expect(src.contains('LifestyleHealthService'), isTrue);
    expect(src.contains("'7d'"), isTrue);
    expect(src.contains("'30d'"), isTrue);
    expect(src.contains("'3m'"), isTrue);
    expect(src.contains("'1y'"), isTrue);
    expect(src.contains('latest_value') || src.contains('latestValue'), isTrue);
  });

  test('11/12 history retention + summary UI', () {
    final src = File(
      'lib/features/lifestyle/presentation/pages/lifestyle_history_page.dart',
    ).readAsStringSync();
    expect(src.contains('/memory/history'), isTrue);
    expect(src.contains('/memory/period-summary'), isTrue);
    expect(src.contains('daily'), isTrue);
    expect(src.contains('weekly'), isTrue);
    expect(src.contains('monthly'), isTrue);
    expect(src.contains('yearly'), isTrue);
    expect(src.contains('historyExplain'), isTrue);
  });

  test('13/14 schedule grouping + reminder PATCH', () {
    final src = File(
      'lib/features/lifestyle/presentation/pages/lifestyle_schedule_page.dart',
    ).readAsStringSync();
    expect(src.contains('today'), isTrue);
    expect(src.contains('tomorrow'), isTrue);
    expect(src.contains('patchReminder'), isTrue);
    expect(src.contains('1440'), isTrue);
  });

  test('15/16 nutrition + exercise safe empty states', () {
    final n = File(
      'lib/features/lifestyle/presentation/pages/lifestyle_nutrition_page.dart',
    ).readAsStringSync();
    final e = File(
      'lib/features/lifestyle/presentation/pages/lifestyle_exercise_page.dart',
    ).readAsStringSync();
    expect(n.contains('noNutrition'), isTrue);
    expect(n.contains('openLifestyleChat'), isTrue);
    expect(e.contains('noExercise'), isTrue);
    expect(e.contains('openLifestyleChat'), isTrue);
  });

  test('17 no frontend clinical/plan inference markers', () {
    final hub = File(
      'lib/features/lifestyle/presentation/pages/lifestyle_page.dart',
    ).readAsStringSync();
    expect(hub.toLowerCase().contains('medically safe'), isFalse);
    expect(hub.toLowerCase().contains('diagnosis'), isFalse);
    final health = File(
      'lib/features/lifestyle/presentation/pages/lifestyle_health_page.dart',
    ).readAsStringSync();
    expect(health.contains('hrStatusLabel'), isTrue);
  });

  testWidgets('top row structure smoke', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Gate3MainIconRow(
            onLifestyle: () {},
            onGadgets: () {},
            onNotifications: () {},
            lang: 'en',
          ),
        ),
      ),
    );
    expect(find.byIcon(Icons.favorite_border), findsNothing);
    expect(find.byIcon(Icons.person_outline), findsOneWidget);
    expect(find.byIcon(Icons.notifications_none_outlined), findsOneWidget);
    expect(find.byType(LifestylePage), findsNothing);
    expect(Gate3Localization('en').notifications, isNotEmpty);
  });
}
