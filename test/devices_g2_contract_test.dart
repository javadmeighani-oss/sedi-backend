import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/locale/sedi_locale_controller.dart';
import 'package:sedi_app/core/network/api_response.dart';
import 'package:sedi_app/core/theme/app_theme.dart';
import 'package:sedi_app/data/dto/device_public_info.dart';
import 'package:sedi_app/data/dto/devices_list_response.dart';
import 'package:sedi_app/data/repositories/devices_repository.dart';
import 'package:sedi_app/features/devices/logic/devices_controller.dart';
import 'package:sedi_app/features/devices/presentation/devices_l10n.dart';
import 'package:sedi_app/features/devices/presentation/pages/devices_page.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/a3_destination_surface.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/a3_page_app_bar.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sedi_app/features/devices/gateway/durable_packet_outbox.dart';
import 'gadgets_connect_g8_test.dart' as g8;

String _read(String relativePath) => File(relativePath).readAsStringSync();

class _FakeDevicesRepository extends DevicesRepository {
  _FakeDevicesRepository() : super(baseUrl: 'http://fake');

  @override
  Future<ApiResponse<DevicesListData?>> list() async {
    final now = DateTime.utc(2026, 1, 1);
    final devices = [
      DevicePublicInfo(
        deviceId: 'SEDI-ECG-000000000001',
        deviceType: 'ECG',
        status: 'active',
        createdAt: now,
        lastSeenAt: now.subtract(const Duration(minutes: 5)),
        deviceCategory: 'SELF',
      ),
      DevicePublicInfo(
        deviceId: 'SEDI-ECG-000000000002',
        deviceType: 'ECG',
        status: 'active',
        createdAt: now,
        deviceCategory: 'OTHER',
        userLabel: 'Mom ECG',
      ),
    ];
    return ApiResponse(
      ok: true,
      data: DevicesListData(devices: devices, count: devices.length),
    );
  }
}

void main() {
  g8.main();
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
    expect(src.contains('A3DestinationSurface.canvas'), isTrue);
    expect(src.contains('AppTheme.gate3PaleOliveBackground'), isFalse);
    expect(src.contains('selfDevices'), isTrue);
    expect(src.contains('otherDevices'), isTrue);
    expect(src.contains('unclassifiedDevices'), isTrue);
    expect(src.contains('connectComingSoon'), isFalse);
    expect(src.contains('l10n.connect'), isTrue);
    expect(src.contains('IgnorePointer'), isFalse);
    expect(src.contains('_ecgConnected'), isFalse);
    // active lifecycle must never be mapped to BLE Connected label by status alone
    expect(src.contains("status == 'active'"), isFalse);
    expect(src.contains('manualDisconnect'), isTrue);
  });

  testWidgets('DevicesPage renders SELF/OTHER headings from backend authority',
      (tester) async {
    await SediLocaleController.instance.setRuntimeLocale(
      'en',
      persistBootstrapCache: false,
    );
    final controller = DevicesController(repo: _FakeDevicesRepository());
    await tester.pumpWidget(
      MaterialApp(home: DevicesPage(controller: controller)),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.byType(A3PageAppBar), findsOneWidget);
    expect(find.text('My gadgets'), findsWidgets);
    expect(find.text('Other gadgets'), findsWidgets);
    expect(find.text('Mom ECG'), findsOneWidget);
    expect(find.text('Connected'), findsNothing);
  });

  testWidgets('FA directionality smoke on DevicesPage', (tester) async {
    await SediLocaleController.instance.setRuntimeLocale(
      'fa',
      persistBootstrapCache: false,
    );
    final controller = DevicesController(repo: _FakeDevicesRepository());
    await tester.pumpWidget(
      MaterialApp(home: DevicesPage(controller: controller)),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('گجت‌ها'), findsOneWidget);
    expect(find.text('گجت‌های من'), findsWidgets);
    expect(
      find.byWidgetPredicate(
        (w) => w is Directionality && w.textDirection == TextDirection.rtl,
      ),
      findsWidgets,
    );
  });

  test('G9 A3 theme continuity + human-readable last sync (en/fa/ar)', () {
    final src = _read('lib/features/devices/presentation/pages/devices_page.dart');
    final native = _read(
      'android/app/src/main/kotlin/com/sedi/app/MainActivity.kt',
    );
    expect(src.contains('A3DestinationSurface.canvas'), isTrue);
    expect(src.contains('AppTheme.gate3PaleOliveBackground'), isFalse);
    expect(src.contains('AppTheme.gate2ButtonOlive'), isTrue);
    expect(src.contains('AppTheme.gate2CardWhite'), isTrue);
    expect(src.contains('A3DestinationCard'), isTrue);
    expect(src.contains('toIso8601String'), isFalse);
    expect(src.contains('AppTheme.dangerRed'), isFalse);
    expect(src.contains('SediBlePermissions.request'), isTrue);
    expect(native.contains('BLUETOOTH_SCAN'), isTrue);
    expect(native.contains('BLUETOOTH_CONNECT'), isTrue);
    expect(native.contains('sedi/ble_permissions'), isTrue);

    final now = DateTime.utc(2026, 9, 12, 12);
    final en = DevicesL10n('en');
    expect(
      en.formatLastSync(now.subtract(const Duration(minutes: 4)), now: now),
      contains('4m ago'),
    );
    expect(en.contactLabel(true), isNot(contains('true')));
    expect(DevicesL10n('fa').formatLastSync(null), contains('همگام'));
    expect(DevicesL10n('ar').isRtl, isTrue);
  });

  testWidgets('G9 DevicesPage white scaffold + olive Connect CTA',
      (tester) async {
    await SediLocaleController.instance.setRuntimeLocale(
      'en',
      persistBootstrapCache: false,
    );
    final controller = DevicesController(repo: _FakeDevicesRepository());
    await tester.pumpWidget(
      MaterialApp(home: DevicesPage(controller: controller)),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    final scaffold = tester.widget<Scaffold>(find.byType(Scaffold).first);
    expect(scaffold.backgroundColor, A3DestinationSurface.canvas);
    expect(find.text('Connect'), findsOneWidget);
    expect(find.textContaining('Last sync'), findsWidgets);
  });

  group('G5 durable outbox', () {
    late Directory tmp;
    late DurablePacketOutbox outbox;

    setUp(() async {
      tmp = await Directory.systemTemp.createTemp('sedi_outbox_');
      outbox = DurablePacketOutbox(
        file: File('${tmp.path}/outbox.json'),
        maxEntries: 2,
      );
    });

    tearDown(() async {
      if (await tmp.exists()) {
        await tmp.delete(recursive: true);
      }
    });

    OutboxEntry entry(String id) => OutboxEntry(
          deviceId: 'SEDI-HR-1',
          clientPacketId: id,
          measuredAtIso: '2026-09-12T10:00:00Z',
          gatewayInstallId: 'gateway-install-abcdefgh',
          packetBody: {
            'client_packet_id': id,
            'measured_at': '2026-09-12T10:00:00Z',
            'transport': 'bluetooth',
            'gateway_install_id': 'gateway-install-abcdefgh',
            'observations': [],
          },
          enqueuedAt: DateTime.utc(2026, 9, 12),
        );

    test('survives restart; client_packet_id stable; bounded queue', () async {
      expect(await outbox.enqueue(entry('pkt-a')), isTrue);
      expect(await outbox.enqueue(entry('pkt-b')), isTrue);
      expect(await outbox.enqueue(entry('pkt-c')), isFalse);

      final reloaded = DurablePacketOutbox(
        file: File('${tmp.path}/outbox.json'),
        maxEntries: 2,
      );
      final all = await reloaded.peekAll();
      expect(all.length, 2);
      expect(all.map((e) => e.clientPacketId).toList(), ['pkt-a', 'pkt-b']);
      expect(await reloaded.enqueue(entry('pkt-a')), isTrue);
      expect((await reloaded.peekAll()).length, 2);
      expect((await reloaded.peekAll()).first.clientPacketId, 'pkt-a');
    });

    test('ACCEPTED/DUPLICATE remove; permanent failure does not retry forever',
        () async {
      await outbox.enqueue(entry('pkt-acc'));
      await outbox.enqueue(entry('pkt-dup'));
      await outbox.remove(deviceId: 'SEDI-HR-1', clientPacketId: 'pkt-acc');
      expect((await outbox.peekAll()).map((e) => e.clientPacketId), ['pkt-dup']);
      await outbox.remove(deviceId: 'SEDI-HR-1', clientPacketId: 'pkt-dup');
      expect((await outbox.peekAll()), isEmpty);

      await outbox.enqueue(entry('pkt-perm'));
      await outbox.markPermanentFailure(
        deviceId: 'SEDI-HR-1',
        clientPacketId: 'pkt-perm',
        reason: 'GATEWAY_AUTH_REJECTED',
      );
      expect((await outbox.peekAll()).single.permanentFailure, isTrue);
      await outbox.dropPermanentFailures();
      expect((await outbox.peekAll()), isEmpty);
    });
  });
}