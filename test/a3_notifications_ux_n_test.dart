import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/notifications/presentation/notification_inbox_l10n.dart';

String _read(String path) => File(path).readAsStringSync();

void main() {
  test('Notifications inbox is a white card destination with weighted detail CTAs',
      () {
    final src = _read(
      'lib/features/notifications/presentation/pages/notification_inbox_page.dart',
    );
    expect(src.contains('A3DestinationSurface.canvas'), isTrue);
    expect(src.contains('gate3PaleOliveBackground'), isFalse);
    expect(src.contains('A3DestinationCard'), isTrue);
    expect(src.contains('listInboxPage'), isTrue);
    expect(src.contains('_loadMore'), isTrue);
    expect(src.contains('_reload'), isTrue);
    expect(src.contains('_markReadOptimistic'), isTrue);
    expect(src.contains("action: 'open_chat'"), isTrue);
    expect(src.contains('AppGateRouter.goToHeart'), isTrue);
    expect(src.contains('wasThisUseful'), isTrue);
    expect(src.contains('continueInChat'), isTrue);
    expect(src.contains('InboxFilter.all'), isTrue);
    expect(src.contains('InboxFilter.unread'), isTrue);
    expect(src.contains('HealthSubject'), isFalse);

    expect(NotificationInboxL10n('en').continueInChat, 'Continue with Sedi');
    expect(NotificationInboxL10n('en').wasThisUseful, 'Was this useful?');
    expect(NotificationInboxL10n('fa').isRtl, isTrue);
    expect(NotificationInboxL10n('ar').isRtl, isTrue);
  });
}
