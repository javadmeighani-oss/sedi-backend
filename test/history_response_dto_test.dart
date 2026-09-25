import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/data/dto/history_response.dart';

void main() {
  test('parses timezone and current_group_key', () {
    final r = HistoryResponse.fromJson({
      'group': 'daily',
      'timezone': 'Asia/Tehran',
      'current_group_key': '2026-09-25',
      'items': [
        {
          'key': '2026-09-25',
          'turns': [
            {
              'id': 7,
              'created_at': '2026-09-25T08:01:00Z',
              'user_message': 'hello',
              'sedi_response': 'hi',
            },
          ],
        },
      ],
    });
    expect(r.timezone, 'Asia/Tehran');
    expect(r.currentGroupKey, '2026-09-25');
    expect(r.items.single.key, '2026-09-25');
  });

  test('timezone and current_group_key are backward-safe when absent', () {
    final r = HistoryResponse.fromJson({
      'group': 'daily',
      'items': [],
    });
    expect(r.timezone, isNull);
    expect(r.currentGroupKey, isNull);
    expect(r.items, isEmpty);
  });

  test('empty timezone and current_group_key become null', () {
    final r = HistoryResponse.fromJson({
      'group': 'daily',
      'timezone': '   ',
      'current_group_key': '',
      'items': [],
    });
    expect(r.timezone, isNull);
    expect(r.currentGroupKey, isNull);
  });

  test('tryParse reads nested data envelope', () {
    final r = HistoryResponse.tryParse({
      'data': {
        'group': 'daily',
        'timezone': 'UTC',
        'current_group_key': '2026-09-24',
        'items': [],
      },
    });
    expect(r, isNotNull);
    expect(r!.timezone, 'UTC');
    expect(r.currentGroupKey, '2026-09-24');
  });
}
