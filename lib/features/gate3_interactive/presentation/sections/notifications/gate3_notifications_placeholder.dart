import 'package:flutter/material.dart';

import '../../../../notification/presentation/pages/notifications_inbox_page.dart';

/// INTERNAL_ONLY alias — wires to canonical Inbox (no duplicate UI).
/// Production A3 opens [NotificationInboxPage] from [Gate3InteractivePage] directly.
class Gate3NotificationsPlaceholder extends StatelessWidget {
  const Gate3NotificationsPlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    return const NotificationsInboxPage();
  }
}
