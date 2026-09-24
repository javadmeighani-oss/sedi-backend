import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/locale/calendar_date_math.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/a3_destination_surface.dart';

String _expectedLocal(String input, String languageCode) {
  final local = DateTime.parse(input).toLocal();
  final y = local.year.toString().padLeft(4, '0');
  final mo = local.month.toString().padLeft(2, '0');
  final d = local.day.toString().padLeft(2, '0');
  final date = CalendarDateMath.formatIsoForLanguage('$y-$mo-$d', languageCode);
  final hh = local.hour.toString().padLeft(2, '0');
  final mm = local.minute.toString().padLeft(2, '0');
  return '$date  $hh:$mm';
}

void main() {
  test('destination timestamps: date-only, local datetime, invalid, blank', () {
    expect(
      A3DestinationSurface.formatIsoTimestamp('2026-09-17', 'en'),
      CalendarDateMath.formatIsoForLanguage('2026-09-17', 'en'),
    );
    expect(
      A3DestinationSurface.formatIsoTimestamp('2026-09-17', 'en'),
      '2026-09-17',
    );
    expect(
      A3DestinationSurface.formatIsoTimestamp('2026-09-17', 'fa'),
      CalendarDateMath.formatIsoForLanguage('2026-09-17', 'fa'),
    );
    expect(
      A3DestinationSurface.formatIsoTimestamp('2026-09-17', 'ar'),
      CalendarDateMath.formatIsoForLanguage('2026-09-17', 'ar'),
    );
    expect(
      A3DestinationSurface.formatIsoTimestamp('2026-09-17', 'fa'),
      isNot(equals('2026-09-17')),
    );
    expect(
      A3DestinationSurface.formatIsoTimestamp('2026-09-17', 'ar'),
      isNot(equals('2026-09-17')),
    );

    const utc = '2026-09-17T12:00:00Z';
    expect(
      A3DestinationSurface.formatIsoTimestamp(utc, 'en'),
      _expectedLocal(utc, 'en'),
    );

    const offset = '2026-09-17T12:00:00+03:30';
    expect(
      A3DestinationSurface.formatIsoTimestamp(offset, 'en'),
      _expectedLocal(offset, 'en'),
    );
    expect(
      A3DestinationSurface.formatIsoTimestamp(offset, 'fa'),
      _expectedLocal(offset, 'fa'),
    );

    expect(
      A3DestinationSurface.formatIsoTimestamp('not-a-date', 'en'),
      'not-a-date',
    );
    expect(A3DestinationSurface.formatIsoTimestamp(null, 'en'), '—');
    expect(A3DestinationSurface.formatIsoTimestamp('   ', 'fa'), '—');
  });
}
