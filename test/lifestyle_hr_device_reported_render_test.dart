import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/lifestyle/presentation/lifestyle_l10n.dart';
import 'package:sedi_app/services/lifestyle/lifestyle_health_service.dart';

void main() {
  group('DEVICE_REPORTED render authority', () {
    test('STABLE + DEVICE_REPORTED → visible authority', () {
      final dto = LifestyleHealthHrDto.fromJson({
        'hr_status': 'STABLE',
        'hr_status_source': 'DEVICE_REPORTED',
        'hr_status_observed_at': '2026-09-17T12:00:00Z',
        'latest_value': 72,
        'range_key': '7d',
        'history': [
          {'bucket_start': '2026-09-10T00:00:00Z', 'avg': 70}
        ],
      });
      expect(dto.isDeviceReportedStatus, isTrue);
      expect(dto.hrStatus, 'STABLE');
      expect(dto.hrStatusSource, 'DEVICE_REPORTED');
      expect(dto.hrStatusObservedAt, isNotNull);
      expect(dto.latestValue, 72);
      expect(dto.history, hasLength(1));
    });

    test('UNSTABLE + DEVICE_REPORTED → visible authority', () {
      final dto = LifestyleHealthHrDto.fromJson({
        'hr_status': 'UNSTABLE',
        'hr_status_source': 'DEVICE_REPORTED',
        'range_key': '7d',
      });
      expect(dto.isDeviceReportedStatus, isTrue);
      expect(dto.hrStatus, 'UNSTABLE');
    });

    test('status present + source null → fail closed', () {
      final dto = LifestyleHealthHrDto.fromJson({
        'hr_status': 'STABLE',
        'range_key': '7d',
        'latest_value': 80,
      });
      expect(dto.isDeviceReportedStatus, isFalse);
      expect(dto.latestValue, 80);
    });

    test('legacy MAD compact only → fail closed', () {
      final dto = LifestyleHealthHrDto.fromJson({
        'hr_status': null,
        'hr_status_source': null,
        'hr_stability_compact': 'UNSTABLE_OR_CHANGED',
        'latest_value': 88,
        'range_key': '7d',
      });
      expect(dto.isDeviceReportedStatus, isFalse);
      expect(dto.hrStabilityCompact, 'UNSTABLE_OR_CHANGED');
      expect(dto.latestValue, 88);
    });

    test('DEVICE_REPORTED + invalid status → fail closed', () {
      final dto = LifestyleHealthHrDto.fromJson({
        'hr_status': 'INSUFFICIENT_DATA',
        'hr_status_source': 'DEVICE_REPORTED',
        'range_key': '7d',
      });
      expect(dto.isDeviceReportedStatus, isFalse);

      final madNamed = LifestyleHealthHrDto.fromJson({
        'hr_status': 'UNSTABLE_OR_CHANGED',
        'hr_status_source': 'DEVICE_REPORTED',
        'range_key': '7d',
      });
      expect(madNamed.isDeviceReportedStatus, isFalse);
    });

    test('null hr_status defaults to null (not INSUFFICIENT_DATA invent)', () {
      final dto = LifestyleHealthHrDto.fromJson({'range_key': '30d'});
      expect(dto.hrStatus, isNull);
      expect(dto.isDeviceReportedStatus, isFalse);
      expect(dto.rangeKey, '30d');
    });
  });

  group('presentation labels EN/FA/AR', () {
    test('device-reported labels localized + RTL flags', () {
      for (final lang in ['en', 'fa', 'ar']) {
        final l10n = LifestyleL10n(lang);
        expect(l10n.deviceReportedHrStatusLabel('STABLE'), isNotEmpty);
        expect(l10n.deviceReportedHrStatusLabel('UNSTABLE'), isNotEmpty);
        if (lang == 'en') {
          expect(l10n.isRtl, isFalse);
          expect(l10n.deviceReportedHrStatusLabel('STABLE'), contains('Stable'));
          expect(
              l10n.deviceReportedHrStatusLabel('UNSTABLE'), contains('Unstable'));
        } else {
          expect(l10n.isRtl, isTrue);
          expect(l10n.deviceReportedHrStatusLabel('STABLE'), isNot(equals('Stable pattern')));
        }
      }
    });
  });

  test('Health page gates on isDeviceReportedStatus; no thresholds', () {
    final src = File(
      'lib/features/lifestyle/presentation/pages/lifestyle_health_page.dart',
    ).readAsStringSync();
    expect(src.contains('isDeviceReportedStatus'), isTrue);
    expect(src.contains('deviceReportedHrStatusLabel'), isTrue);
    expect(src.contains('hr_stability_compact'), isFalse);
    expect(src.contains('heart_rate_thresholds'), isFalse);
    expect(src.contains('>100'), isFalse);
    expect(src.contains('<60'), isFalse);
  });
}
