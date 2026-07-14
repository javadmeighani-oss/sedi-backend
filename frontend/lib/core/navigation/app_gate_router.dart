import 'package:flutter/material.dart';

import '../../features/auth_otp/presentation/pages/otp_login_page.dart';
import '../../features/gate3_interactive/presentation/pages/gate3_interactive_page.dart';
import '../../features/intro/presentation/pages/intro_page.dart';
import '../notifications/notification_launch_context.dart';
import 'app_gate.dart';

/// Central navigation for the 3-gate frontend architecture.
///
/// Use [replaceWithGate] / [goToLogin] / [goToHeart] instead of scattering
/// `Navigator.pushReplacement` calls across feature pages.
class AppGateRouter {
  AppGateRouter._();

  static Widget buildGatePage(
    SediAppGate gate, {
    String? initialMessage,
    bool fromNotification = false,
    int? notificationId,
    NotificationLaunchContext? notificationLaunch,
  }) {
    switch (gate) {
      case SediAppGate.splash:
        return const IntroPage();
      case SediAppGate.login:
        return const OtpLoginPage();
      case SediAppGate.heart:
        return Gate3InteractivePage(
          initialMessage: initialMessage,
          fromNotification: fromNotification || notificationLaunch != null,
          notificationId:
              notificationId ?? notificationLaunch?.sourceNotificationId,
          notificationLaunch: notificationLaunch,
        );
    }
  }

  /// Replace the entire navigation stack with [gate].
  static void replaceWithGate(
    BuildContext context,
    SediAppGate gate, {
    String? initialMessage,
    bool fromNotification = false,
    int? notificationId,
    NotificationLaunchContext? notificationLaunch,
  }) {
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(
        builder: (_) => buildGatePage(
          gate,
          initialMessage: initialMessage,
          fromNotification: fromNotification,
          notificationId: notificationId,
          notificationLaunch: notificationLaunch,
        ),
      ),
      (_) => false,
    );
  }

  static void goToLogin(BuildContext context) {
    replaceWithGate(context, SediAppGate.login);
  }

  static void goToHeart(
    BuildContext context, {
    String? initialMessage,
    bool fromNotification = false,
    int? notificationId,
    NotificationLaunchContext? notificationLaunch,
  }) {
    replaceWithGate(
      context,
      SediAppGate.heart,
      initialMessage: initialMessage,
      fromNotification: fromNotification,
      notificationId: notificationId,
      notificationLaunch: notificationLaunch,
    );
  }

  /// Splash-only cube transition into Gate 2 or Gate 3.
  static void transitionFromSplash(
    BuildContext context,
    SediAppGate gate, {
    required Widget splashPage,
    String? initialMessage,
    NotificationLaunchContext? notificationLaunch,
  }) {
    assert(gate != SediAppGate.splash);
    Navigator.of(context).pushReplacement(
      PageRouteBuilder(
        pageBuilder: (context, animation, secondaryAnimation) => buildGatePage(
          gate,
          initialMessage: initialMessage,
          fromNotification: notificationLaunch != null,
          notificationId: notificationLaunch?.sourceNotificationId,
          notificationLaunch: notificationLaunch,
        ),
        transitionDuration: const Duration(milliseconds: 600),
        reverseTransitionDuration: const Duration(milliseconds: 600),
        opaque: false,
        transitionsBuilder: (context, animation, secondaryAnimation, child) {
          final curvedAnimation = CurvedAnimation(
            parent: animation,
            curve: Curves.easeInOutCubic,
          );
          final exitAnimation = CurvedAnimation(
            parent: secondaryAnimation,
            curve: Curves.easeInOutCubic,
          );
          return Stack(
            children: [
              SlideTransition(
                position: Tween<Offset>(
                  begin: Offset.zero,
                  end: const Offset(-1.0, 0.0),
                ).animate(exitAnimation),
                child: FadeTransition(
                  opacity: exitAnimation,
                  child: splashPage,
                ),
              ),
              SlideTransition(
                position: Tween<Offset>(
                  begin: const Offset(1.0, 0.0),
                  end: Offset.zero,
                ).animate(curvedAnimation),
                child: FadeTransition(
                  opacity: curvedAnimation,
                  child: child,
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}
