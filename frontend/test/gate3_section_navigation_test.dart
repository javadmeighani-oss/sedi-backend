import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/data/dto/gate3/caregiver_dto.dart';
import 'package:sedi_app/features/gate3_interactive/logic/gate3_phone_utils.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/gate3_sections_localization.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/sections/settings/gate3_settings_page.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/gate3_section_scaffold.dart';

void main() {
  testWidgets('Gate3SettingsPage shows close contacts entry', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Gate3SettingsPage(lang: 'en'),
      ),
    );
    expect(find.text('Close contacts'), findsOneWidget);
    expect(find.byType(Gate3SectionScaffold), findsOneWidget);
  });

  testWidgets('Gate3SectionScaffold back pops route', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) {
            return Scaffold(
              body: Center(
                child: ElevatedButton(
                  onPressed: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => Gate3SectionScaffold(
                          lang: 'en',
                          title: 'Test',
                          body: const Text('inner'),
                        ),
                      ),
                    );
                  },
                  child: const Text('open'),
                ),
              ),
            );
          },
        ),
      ),
    );

    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.text('inner'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.arrow_back_rounded));
    await tester.pumpAndSettle();
    expect(find.text('open'), findsOneWidget);
  });

  test('manual call disabled when phone invalid', () {
    expect(Gate3PhoneUtils.isValid(''), isFalse);
    const contact = CaregiverDto(id: 1, name: 'A');
    expect(contact.phone == null || !Gate3PhoneUtils.isValid(contact.phone!), isTrue);
  });

  test('caregiver preference fields map from API json', () {
    final dto = CaregiverDto.fromJson({
      'id': 1,
      'name': 'Sara',
      'phone': '+989121234567',
      'relationship': 'sister',
      'notify_daily_status': true,
      'notify_emergency': false,
      'notify_care_summary': true,
      'is_active': true,
    });
    expect(dto.notifyDailyStatus, isTrue);
    expect(dto.notifyEmergency, isFalse);
    expect(dto.notifyCareSummary, isTrue);
  });
}
