import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/lifestyle/presentation/lifestyle_l10n.dart';

String _read(String path) => File(path).readAsStringSync();

void main() {
  test('L5 weekly plan keeps Talk-to-Sedi contract on a white card canvas', () {
    final view = _read(
      'lib/features/lifestyle/presentation/widgets/lifestyle_weekly_plan_view.dart',
    );
    expect(view.contains('A3DestinationSurface.canvas'), isTrue);
    expect(view.contains('gate3PaleOliveBackground'), isFalse);
    expect(view.contains("'active'"), isTrue);
    expect(view.contains("'empty'"), isTrue);
    expect(view.contains("'review_due'"), isTrue);
    expect(view.contains("'unavailable'"), isTrue);
    expect(view.contains('openLifestyleChat'), isTrue);
    expect(view.contains('starterMessage: starter'), isTrue);
    expect(view.contains('nutritionChatStarter'), isTrue);
    expect(view.contains('exerciseChatStarter'), isTrue);
    expect(view.contains('talkToCreate'), isTrue);
    expect(view.contains('l10n.openChat'), isTrue);
    expect(view.contains('DateTime.now()'), isFalse);
    expect(view.contains('Gate3InteractivePage'), isFalse);
    expect(view.contains('sendUserMessage'), isFalse);
    expect(view.contains('initialDraft'), isFalse);

    final n = _read(
      'lib/features/lifestyle/presentation/pages/lifestyle_nutrition_page.dart',
    );
    final e = _read(
      'lib/features/lifestyle/presentation/pages/lifestyle_exercise_page.dart',
    );
    expect(n.contains('LifestyleWeeklyPlanView'), isTrue);
    expect(e.contains('LifestyleWeeklyPlanView'), isTrue);

    expect(LifestyleL10n('en').nutritionChatStarter.isNotEmpty, isTrue);
    expect(LifestyleL10n('en').exerciseChatStarter.isNotEmpty, isTrue);
    expect(LifestyleL10n('en').talkToCreate.toLowerCase().contains('sedi'), isTrue);
  });
}
