import 'package:flutter/material.dart';

import '../../../notification/presentation/pages/notifications_inbox_page.dart';

/// Gate 4 entrypoint for Notifications.
///
/// Ownership rule:
/// - Gate 3 may show the Notifications icon as a primary entry.
/// - Gate 4 owns the destination/feature UI.
///
/// V1 keeps the existing production inbox behind this Gate 4 page
/// so ownership is explicit without breaking notification UX.
class Gate4NotificationsPlaceholderPage extends StatelessWidget {
  const Gate4NotificationsPlaceholderPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const NotificationsInboxPage();
  }
}
