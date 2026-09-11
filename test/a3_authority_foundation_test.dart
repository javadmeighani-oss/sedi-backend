import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/locale/sedi_locale_controller.dart';
import 'package:sedi_app/core/locale/sedi_locale_registry.dart';
import 'package:sedi_app/data/dto/chat/chat_send_request.dart';
import 'package:sedi_app/data/dto/chat/chat_send_response.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/gate3_localization.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    SediLocaleController.instance.debugResetForTest();
  });

  test('ChatSendRequest omits body user_id and carries source_notification_id', () {
    final json = const ChatSendRequest(
      message: 'hi',
      sourceNotificationId: 17,
    ).toJson();
    expect(json.containsKey('user_id'), isFalse);
    expect(json['source_notification_id'], 17);
    expect(json['message'], 'hi');
  });

  test('Gate3Localization consumes registry RTL via global locale codes', () async {
    await SediLocaleController.instance.setRuntimeLocale('fa', persistBootstrapCache: false);
    final l10n = Gate3Localization(SediLocaleController.instance.languageCode);
    expect(l10n.isRtl, isTrue);
    expect(SediLocaleRegistry.resolve('fa').defaultCalendar, 'jalali');
  });

  test('A3 language follows SediLocaleController not independent authority', () async {
    await SediLocaleController.instance.setRuntimeLocale('ar', persistBootstrapCache: false);
    expect(SediLocaleController.instance.languageCode, 'ar');
    expect(Gate3Localization('ar').isRtl, isTrue);
    await SediLocaleController.instance.setRuntimeLocale('en', persistBootstrapCache: false);
    expect(Gate3Localization('en').isRtl, isFalse);
  });

  test('ChatSendResponse parses stream final payload fields', () {
    final r = ChatSendResponse.fromJson({
      'message': 'Hello',
      'language': 'fa',
      'source_notification_id': 9,
      'first_intro': false,
      'intro_completed': true,
      'proactive_opener': 'Welcome back',
    });
    expect(r.message, 'Hello');
    expect(r.sourceNotificationId, 9);
    expect(r.introCompleted, isTrue);
    expect(r.proactiveOpener, 'Welcome back');
  });
}
