import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/health_subject/sedi_health_subject.dart';
import 'package:sedi_app/core/health_subject/sedi_health_subject_controller.dart';
import 'package:sedi_app/data/dto/chat/chat_send_request.dart';
import 'package:sedi_app/data/dto/device_public_info.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/gate3_localization.dart';

void main() {
  setUp(() {
    SediHealthSubjectController.instance.debugResetForTest();
  });

  test('default active subject is SELF', () {
    final c = SediHealthSubjectController.instance;
    c.debugSeedForTest(subjects: [
      const SediHealthSubject(
        id: 1,
        displayName: 'Me',
        subjectKind: 'self',
        status: 'active',
        accessRole: 'SELF',
      ),
      const SediHealthSubject(
        id: 2,
        displayName: 'Alex',
        subjectKind: 'managed',
        status: 'active',
        accessRole: 'MANAGER',
      ),
    ]);
    expect(c.selfSubject?.id, 1);
    expect(c.activeSubject?.id, 1);
    expect(c.isActiveSelf, isTrue);
  });

  test('select OTHER bumps generation and clears SELF active', () {
    final c = SediHealthSubjectController.instance;
    c.debugSeedForTest(subjects: [
      const SediHealthSubject(
          id: 1, displayName: 'Me', subjectKind: 'self', status: 'active', accessRole: 'SELF'),
      const SediHealthSubject(
          id: 2,
          displayName: 'Sam',
          subjectKind: 'managed',
          status: 'active',
          accessRole: 'MANAGER'),
    ]);
    final g0 = c.generation;
    c.selectSubject(2);
    expect(c.activeSubject?.id, 2);
    expect(c.isActiveSelf, isFalse);
    expect(c.generation, greaterThan(g0));
    expect(c.activeSubject!.visibleName, 'Sam');
  });

  test('ChatSendRequest carries health_subject_id', () {
    final json = const ChatSendRequest(
      message: 'hi',
      healthSubjectId: 9,
    ).toJson();
    expect(json['health_subject_id'], 9);
    expect(json.containsKey('user_id'), isFalse);
  });

  test('DevicePublicInfo parses health_subject_id', () {
    final d = DevicePublicInfo.fromJson({
      'device_id': 'd1',
      'device_type': 'ecg',
      'status': 'active',
      'created_at': '2026-01-01T00:00:00Z',
      'health_subject_id': 42,
    });
    expect(d.healthSubjectId, 42);
  });

  test('no hard-coded Mother in Gate3 subject l10n', () {
    for (final lang in ['en', 'fa', 'ar']) {
      final l10n = Gate3Localization(lang);
      expect(l10n.activeSubjectSelf.toLowerCase().contains('mother'), isFalse);
      expect(l10n.selectSubject.toLowerCase().contains('mother'), isFalse);
      expect(l10n.lifestyleOtherUnavailable.toLowerCase().contains('mother'), isFalse);
    }
  });

  test('OTHER lifestyle unavailable string exists', () {
    expect(Gate3Localization('en').lifestyleOtherUnavailable, isNotEmpty);
  });
}
