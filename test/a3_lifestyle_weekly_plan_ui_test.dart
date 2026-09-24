import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/locale/calendar_date_math.dart';
import 'package:sedi_app/core/theme/app_theme.dart';
import 'package:sedi_app/data/dto/lifestyle/lifestyle_weekly_plan_dto.dart';
import 'package:sedi_app/features/auth_otp/presentation/birth_calendar_helper.dart';
import 'package:sedi_app/features/lifestyle/presentation/lifestyle_l10n.dart';

void main() {
  group('LifestyleWeeklyPlanDto', () {
    test('parses nutrition + exercise domains from shared payload', () {
      final dto = LifestyleWeeklyPlanDto.fromJson({
        'cycle_start': '2026-03-10',
        'cycle_end': '2026-03-16',
        'timezone': 'Asia/Tehran',
        'state': 'active',
        'review_due': false,
        'days': [
          {
            'local_date': '2026-03-10',
            'day_index': 1,
            'nutrition': [
              {
                'title': 'Oats',
                'status': 'ACTIVE',
                'action_type': 'meal',
                'local_time': '08:00',
                'meal_slot': 'breakfast',
              }
            ],
            'exercise': [
              {
                'title': 'Walk',
                'status': 'ACTIVE',
                'action_type': 'activity',
                'activity_type': 'walk',
                'activity_title': 'Walk',
                'duration_minutes': 30,
                'local_time': '18:00',
              }
            ],
          },
          {
            'local_date': '2026-03-11',
            'day_index': 2,
            'nutrition': [],
            'exercise': [],
          },
        ],
      });
      expect(dto.state, 'active');
      expect(dto.cycleStart, '2026-03-10');
      expect(dto.days.length, 2);
      expect(dto.days.first.nutrition.single.title, 'Oats');
      expect(dto.days.first.nutrition.single.mealSlot, 'breakfast');
      expect(dto.days.first.exercise.single.durationMinutes, 30);
      expect(dto.days[1].nutrition, isEmpty);
      expect(dto.days[1].exercise, isEmpty);
    });

    test('states empty / review_due / unavailable parse without inventing days',
        () {
      for (final state in ['empty', 'review_due', 'unavailable']) {
        final dto = LifestyleWeeklyPlanDto.fromJson({
          'state': state,
          'review_due': state == 'review_due',
          'days': [],
        });
        expect(dto.state, state);
        expect(dto.days, isEmpty);
      }
    });
  });

  group('shared weekly service + presentation authority', () {
    test('one weekly-plan service endpoint; pages reuse shared view', () {
      final svc = File(
        'lib/services/lifestyle/lifestyle_weekly_plan_service.dart',
      ).readAsStringSync();
      expect(svc.contains('/lifestyle/weekly-plan'), isTrue);
      expect(svc.contains('LifestyleWeeklyPlanDto'), isTrue);

      final n = File(
        'lib/features/lifestyle/presentation/pages/lifestyle_nutrition_page.dart',
      ).readAsStringSync();
      final e = File(
        'lib/features/lifestyle/presentation/pages/lifestyle_exercise_page.dart',
      ).readAsStringSync();
      expect(n.contains('LifestyleWeeklyPlanView'), isTrue);
      expect(e.contains('LifestyleWeeklyPlanView'), isTrue);
      expect(n.contains('Mon'), isFalse);
      expect(e.contains('Mon'), isFalse);
      expect(n.contains('— —'), isFalse);
      expect(e.contains('— —'), isFalse);
    });

    test('presentation has required states; no device-TZ Today marker', () {
      final view = File(
        'lib/features/lifestyle/presentation/widgets/lifestyle_weekly_plan_view.dart',
      ).readAsStringSync();
      expect(view.contains("'active'"), isTrue);
      expect(view.contains("'empty'"), isTrue);
      expect(view.contains("'review_due'"), isTrue);
      expect(view.contains("'unavailable'"), isTrue);
      expect(view.contains('DateTime.now()'), isFalse);
      expect(view.contains('A3DestinationSurface.canvas'), isTrue);
      expect(view.contains('gate3PaleOliveBackground'), isFalse);
      expect(view.contains('AppTheme.gate2ButtonOlive'), isTrue);
      expect(view.contains('A3DestinationCard'), isTrue);
      expect(view.contains('CalendarDateMath'), isTrue);
      expect(view.contains('BirthCalendarHelper'), isFalse);
    });

    test('no frontend plan / clinical inference markers in weekly UI', () {
      final view = File(
        'lib/features/lifestyle/presentation/widgets/lifestyle_weekly_plan_view.dart',
      ).readAsStringSync();
      final lower = view.toLowerCase();
      expect(lower.contains('diagnosis'), isFalse);
      expect(lower.contains('medically'), isFalse);
      expect(lower.contains('cycle phase'), isFalse);
      expect(view.contains('generatePlan'), isFalse);
    });
  });

  group('locale weekdays + calendars', () {
    test('weekdays localized en/fa/ar from ISO weekday', () {
      expect(LifestyleL10n('en').weekdayShort(1), 'Mon');
      expect(LifestyleL10n('fa').weekdayShort(1), isNot(equals('Mon')));
      expect(LifestyleL10n('ar').weekdayShort(1), isNot(equals('Mon')));
      expect(LifestyleL10n('fa').isRtl, isTrue);
      expect(LifestyleL10n('ar').isRtl, isTrue);
      expect(LifestyleL10n('en').isRtl, isFalse);
    });

    test('Gregorian / Jalali / Hijri presentation from ISO', () {
      const iso = '2026-03-10';
      expect(CalendarDateMath.formatIsoForLanguage(iso, 'en'), '2026-03-10');
      final jalali = CalendarDateMath.formatIsoForLanguage(iso, 'fa');
      final hijri = CalendarDateMath.formatIsoForLanguage(iso, 'ar');
      expect(jalali, isNot(equals('2026-03-10')));
      expect(hijri, isNot(equals('2026-03-10')));
      expect(jalali.contains('/'), isTrue);
      expect(hijri.contains('/'), isTrue);
      // BirthCalendarHelper public API preserved via delegate.
      final j = BirthCalendarHelper.gregorianToJalali(2026, 3, 10);
      final h = BirthCalendarHelper.gregorianToHijri(2026, 3, 10);
      expect(j.length, 3);
      expect(h.length, 3);
      expect(
        CalendarDateMath.gregorianToJalali(2026, 3, 10),
        BirthCalendarHelper.gregorianToJalali(2026, 3, 10),
      );
    });

    test('weekday derives from backend local_date (not hard-coded week list)', () {
      expect(CalendarDateMath.weekdayFromIso('2026-03-10'), 2); // Tue
      expect(LifestyleL10n('en').weekdayShort(2), 'Tue');
    });
  });

  group('chat lifestyle starter handoff', () {
    test('Gate3 page/composer wire draft without auto-send', () {
      final page = File(
        'lib/features/gate3_interactive/presentation/pages/gate3_interactive_page.dart',
      ).readAsStringSync();
      final composer = File(
        'lib/features/gate3_interactive/presentation/widgets/gate3_composer.dart',
      ).readAsStringSync();
      final lifestyle = File(
        'lib/features/lifestyle/presentation/pages/lifestyle_page.dart',
      ).readAsStringSync();

      expect(page.contains('initialDraft'), isTrue);
      expect(page.contains('_composerDraftSeed'), isTrue);
      expect(page.contains('Gate3ComposerDraftBus'), isTrue);
      expect(page.contains('Gate3AssistantStarterBus'), isTrue);
      expect(page.contains('insertPresentationAssistantMessage'), isTrue);
      expect(page.contains('initialMessage'), isTrue);
      expect(page.contains('initialMessage: widget.initialMessage'), isTrue);
      expect(composer.contains('initialText'), isTrue);
      expect(composer.contains('onSendText'), isTrue);
      // No auto-send of initialText in initState.
      final init = RegExp(
        r'void initState\(\)[\s\S]*?_onTextChanged\(\);',
      ).firstMatch(composer)?.group(0);
      expect(init, isNotNull);
      expect(init!.contains('onSendText'), isFalse);
      expect(init.contains('_send'), isFalse);

      expect(lifestyle.contains('starterMessage'), isTrue);
      expect(lifestyle.contains('popUntil'), isTrue);
      expect(lifestyle.contains('Gate3AssistantStarterBus'), isTrue);
      expect(lifestyle.contains('Gate3InteractivePage(initialDraft:'), isFalse);
      expect(LifestyleL10n('en').nutritionChatStarter.isNotEmpty, isTrue);
      expect(LifestyleL10n('en').exerciseChatStarter.isNotEmpty, isTrue);
      expect(LifestyleL10n('fa').nutritionChatStarter.contains('تغذیه'), isTrue);
    });
  });

  test('AppTheme pale olive still present', () {
    expect(AppTheme.gate3PaleOliveBackground, isNotNull);
  });
}
