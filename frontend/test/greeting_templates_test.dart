import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/chat/logic/greeting_templates.dart';

void main() {
  group('getIntroGreeting', () {
    test('FA contains صدی (never سدی)', () {
      final text = getIntroGreeting('fa');
      expect(text, contains('صدی'));
      expect(text, isNot(contains('سدی')));
    });

    test('FA greeting is short and professional', () {
      final text = getIntroGreeting('fa');
      expect(text, contains('همراه هوشمند سلامت'));
      expect(text.length, lessThan(120));
    });

    test('EN contains Sedi', () {
      final text = getIntroGreeting('en');
      expect(text, contains('Sedi'));
    });

    test('EN greeting is short and professional', () {
      final text = getIntroGreeting('en');
      expect(text.toLowerCase(), contains('health companion'));
      expect(text.length, lessThan(140));
    });

    test('AR contains صدی (never سدی)', () {
      final text = getIntroGreeting('ar');
      expect(text, contains('صدی'));
      expect(text, isNot(contains('سدی')));
    });

    test('unknown locale defaults to EN greeting', () {
      final text = getIntroGreeting('de');
      expect(text, contains('Sedi'));
    });
  });
}
