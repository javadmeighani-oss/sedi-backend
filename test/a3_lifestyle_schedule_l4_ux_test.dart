import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

String _read(String path) => File(path).readAsStringSync();

void main() {
  test('L4 Schedule uses structured event cards and locked reminder presets', () {
    final src = _read(
      'lib/features/lifestyle/presentation/pages/lifestyle_schedule_page.dart',
    );
    expect(src.contains('A3DestinationSurface.canvas'), isTrue);
    expect(src.contains('gate3PaleOliveBackground'), isFalse);
    expect(src.contains('A3DestinationCard'), isTrue);
    expect(src.contains("'today'"), isTrue);
    expect(src.contains("'tomorrow'"), isTrue);
    expect(src.contains("'week'"), isTrue);
    expect(src.contains("'later'"), isTrue);
    expect(src.contains('patchReminder'), isTrue);
    expect(src.contains('1440'), isTrue);
    expect(src.contains('60'), isTrue);
    expect(src.contains('join(\' · \')'), isFalse);
    expect(src.contains('LifestyleScheduleService'), isTrue);
    expect(src.contains('listI8Actions'), isTrue);
    expect(src.contains('e.location'), isTrue);
    expect(src.contains('e.eventType'), isTrue);
    expect(src.contains('e.title'), isTrue);
  });
}
