import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/utils/brand_name.dart';

void main() {
  group('sediBrandName', () {
    test('fa returns صدی', () {
      expect(sediBrandName('fa'), 'صدی');
      expect(sediBrandName('FA'), 'صدی');
    });

    test('ar returns صدی', () {
      expect(sediBrandName('ar'), 'صدی');
      expect(sediBrandName('AR'), 'صدی');
    });

    test('en returns Sedi', () {
      expect(sediBrandName('en'), 'Sedi');
      expect(sediBrandName('EN'), 'Sedi');
    });

    test('unknown locale defaults to Sedi', () {
      expect(sediBrandName('de'), 'Sedi');
      expect(sediBrandName('fr'), 'Sedi');
      expect(sediBrandName(''), 'Sedi');
    });
  });
}
