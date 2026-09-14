import 'package:flutter/material.dart';

import '../../../notification/presentation/pages/notifications_inbox_page.dart';

/// Gate 3 primary Notifications entry — wires to canonical Inbox (no duplicate UI).
class Gate3NotificationsPlaceholder extends StatelessWidget {
  const Gate3NotificationsPlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    return const NotificationsInboxPage();
  }
}
