import 'dart:io';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/device/mobile_install_id_store.dart';
import 'package:sedi_app/core/network/api_response.dart';
import 'package:sedi_app/core/utils/user_profile_manager.dart';
import 'package:sedi_app/data/models/user_profile.dart';
import 'package:sedi_app/data/repositories/notification_repository.dart';
import 'package:sedi_app/features/devices/gateway/gateway_install_id_store.dart';
import 'package:sedi_app/services/push/push_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _RecordingRepo extends NotificationRepository {
  _RecordingRepo() : super(baseUrl: 'http://127.0.0.1');

  String? lastDeviceId;
  String? lastToken;
  int calls = 0;

  @override
  Future<ApiResponse<Map<String, dynamic>?>> registerToken({
    required int userId,
    required String fcmToken,
    String? deviceId,
    String? appVersion,
  }) async {
    calls += 1;
    lastDeviceId = deviceId;
    lastToken = fcmToken;
    return ApiResponse(ok: true, statusCode: 200, data: {'ok': true});
  }
}

class _FixedInstallStore extends MobileInstallIdStore {
  _FixedInstallStore(this.id);

  final String id;

  @override
  Future<String> getOrCreate() async => id;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
    await UserProfileManager.clearProfile();
  });

  test('shared install id uses existing secure-storage key', () {
    final src = File('lib/core/device/mobile_install_id_store.dart')
        .readAsStringSync();
    expect(src.contains("storageKey = 'sedi_gateway_install_id_v1'"), isTrue);
    expect(MobileInstallIdStore.storageKey, 'sedi_gateway_install_id_v1');
    expect(GatewayInstallIdStore.storageKey, MobileInstallIdStore.storageKey);
  });

  test('repeated getOrCreate reuses same install id', () async {
    final store = MobileInstallIdStore();
    final a = await store.getOrCreate();
    final b = await store.getOrCreate();
    expect(a.length, greaterThanOrEqualTo(8));
    expect(b, a);
    expect(await store.peek(), a);
  });

  test('gateway store delegates to shared core store', () async {
    final core = MobileInstallIdStore();
    final gateway = GatewayInstallIdStore(store: core);
    final id = await gateway.getOrCreate();
    expect(await core.peek(), id);
    expect(await gateway.peek(), id);
  });

  test('push registration sends non-empty stable device_id', () async {
    await UserProfileManager.saveProfile(
      UserProfile(userId: 7, isVerified: true, phoneNumber: '+989120000000'),
    );
    final repo = _RecordingRepo();
    final store = _FixedInstallStore('install-stable-aaaaaaaa');
    final res = await registerFcmTokenToBackend(
      'fcm-token-aaaaaaaaaaaaaaaa',
      repository: repo,
      installIdStore: store,
    );
    expect(res.ok, isTrue);
    expect(repo.calls, 1);
    expect(repo.lastDeviceId, 'install-stable-aaaaaaaa');
    expect(repo.lastDeviceId, isNotEmpty);
  });

  test('token refresh registration uses same installation id', () async {
    await UserProfileManager.saveProfile(
      UserProfile(userId: 7, isVerified: true, phoneNumber: '+989120000000'),
    );
    final repo = _RecordingRepo();
    final store = _FixedInstallStore('install-stable-bbbbbbbb');
    await registerFcmTokenToBackend(
      'fcm-token-one',
      repository: repo,
      installIdStore: store,
    );
    await registerFcmTokenToBackend(
      'fcm-token-rotated',
      repository: repo,
      installIdStore: store,
    );
    expect(repo.calls, 2);
    expect(repo.lastDeviceId, 'install-stable-bbbbbbbb');
    expect(repo.lastToken, 'fcm-token-rotated');
  });

  test('onTokenRefresh uses shared register path', () {
    final boot = File(
      'lib/core/notifications/notification_bootstrap.dart',
    ).readAsStringSync();
    expect(boot.contains('onTokenRefresh'), isTrue);
    expect(boot.contains('_registerTokenOnStart'), isTrue);
    expect(boot.contains('registerFcmTokenToBackend'), isTrue);
    final push = File('lib/services/push/push_service.dart').readAsStringSync();
    expect(push.contains('deviceId: installId'), isTrue);
    expect(push.contains('MobileInstallIdStore'), isTrue);
  });
}
