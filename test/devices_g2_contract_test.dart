import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/locale/sedi_locale_controller.dart';
import 'package:sedi_app/features/devices/presentation/pages/devices_page.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/a3_page_app_bar.dart';
import 'package:shared_preferences/shared_preferences.dart';

String _read(String relativePath) => File(relativePath).readAsStringSync();

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    SediLocaleController.instance.debugResetForTest();
  });

  test('DevicesRepository is JWT-only without user_id query', () {
    final src = _read('lib/data/repositories/devices_repository.dart');
    expect(src.contains('_userQuery'), isFalse);
    expect(src.contains("'user_id'"), isFalse);
    expect(src.contains('"user_id"'), isFalse);
    expect(src.contains('required int userId'), isFalse);
    expect(src.contains('updatePresentation'), isTrue);
    expect(src.contains("'/devices/\$deviceId'"), isTrue);
    expect(src.contains("'device_category'"), isTrue);
    expect(src.contains('_client.patch'), isTrue);
    expect(src.contains('health_subject_id'), isFalse);
  });

  test('DevicesPage contract: locale + category grouping, no BLE Connected', () {
    final src = _read('lib/features/devices/presentation/pages/devices_page.dart');
    expect(src.contains('SediHealthSubjectController'), isFalse);
    expect(src.contains('UserPreferences'), isFalse);
    expect(src.contains('SediLocaleController'), isTrue);
    expect(src.contains('A3PageAppBar'), isTrue);
    expect(src.contains('selfDevices'), isTrue);
    expect(src.contains('otherDevices'), isTrue);
    expect(src.contains('unclassifiedDevices'), isTrue);
    expect(src.contains("'Connected'"), isFalse);
    expect(src.contains('"Connected"'), isFalse);
    expect(src.contains('_ecgConnected'), isFalse);
    expect(src.contains('connectComingSoon'), isTrue);
  });

  testWidgets('DevicesPage renders SELF/OTHER headings from backend authority',
      (tester) async {
    await SediLocaleController.instance.setRuntimeLocale('en',
        persistBootstrapCache: false);
    await tester.pumpWidget(
      const MaterialApp(home: DevicesPage()),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.byType(A3PageAppBar), findsOneWidget);
    expect(find.text('My gadgets'), findsWidgets);
    expect(find.text('Other gadgets'), findsWidgets);
    expect(find.text('Connected'), findsNothing);
  });

  testWidgets('FA directionality smoke on DevicesPage', (tester) async {
    await SediLocaleController.instance.setRuntimeLocale('fa',
        persistBootstrapCache: false);
    await tester.pumpWidget(
      const MaterialApp(home: DevicesPage()),
    );
    await tester.pump();
    expect(find.text('گجت‌ها'), findsOneWidget);
    expect(find.text('گجت‌های من'), findsWidgets);
  });
}
