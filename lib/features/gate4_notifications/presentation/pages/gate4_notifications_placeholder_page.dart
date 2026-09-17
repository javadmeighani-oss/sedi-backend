import 'package:flutter/material.dart';

import '../../../notification/presentation/pages/notifications_inbox_page.dart';

/// INTERNAL_ONLY alias — not a product router entry (R3).
///
/// Thin wrapper to canonical [NotificationsInboxPage] / [NotificationInboxPage].
/// Production A3 Smart Notifications opens [NotificationInboxPage] directly
/// from [Gate3InteractivePage]. Do not register this as a parallel root route.
class Gate4NotificationsPlaceholderPage extends StatelessWidget {
  const Gate4NotificationsPlaceholderPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const NotificationsInboxPage();
  }
}
