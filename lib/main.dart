import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'app.dart';
import 'core/notifications/notification_bootstrap.dart';

/// App entry — shared bootstrap only.
/// A1 session/visual logic lives under intro + SessionGateResolver.
/// A4 notification/FCM bootstrap is isolated in [NotificationBootstrap].
void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  try {
    await Firebase.initializeApp();
    debugPrint('[FCM] Firebase initialized ok');
    await NotificationBootstrap.setup();
  } catch (e) {
    // Graceful if google-services.json missing / Firebase unavailable.
    debugPrint('[main] Firebase/FCM setup skipped: $e');
  }

  runApp(const SediApp());
}
