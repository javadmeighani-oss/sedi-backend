import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/navigation/app_gate.dart';
import 'package:sedi_app/core/navigation/app_gate_router.dart';
import 'package:sedi_app/features/auth_otp/presentation/pages/otp_login_page.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/pages/gate3_interactive_page.dart';
import 'package:sedi_app/features/intro/presentation/pages/intro_page.dart';

String _read(String relativePath) => File(relativePath).readAsStringSync();

/// Production lib paths that must never import quarantined legacy product pages.
const _canonicalProductSurfaces = <String>[
  'lib/app.dart',
  'lib/main.dart',
  'lib/core/navigation/app_gate_router.dart',
  'lib/core/navigation/session_gate_resolver.dart',
  'lib/core/auth/auth_helper.dart',
  'lib/core/notifications/notification_bootstrap.dart',
  'lib/features/intro/presentation/pages/intro_page.dart',
  'lib/features/auth_otp/presentation/pages/otp_login_page.dart',
  'lib/features/gate3_interactive/presentation/pages/gate3_interactive_page.dart',
  'lib/features/gate3_interactive/presentation/pages/gate3_profile_page.dart',
  'lib/features/gate3_interactive/presentation/widgets/gate3_main_icon_row.dart',
  'lib/features/lifestyle/presentation/pages/lifestyle_page.dart',
  'lib/features/lifestyle/presentation/pages/lifestyle_health_page.dart',
  'lib/features/notifications/presentation/pages/notification_inbox_page.dart',
];

const _legacyPageImportNeedles = <String>[
  'chat/presentation/pages/chat_page.dart',
  'onboarding/presentation/pages/onboarding_page.dart',
  'user_verification/presentation/pages/user_verification_page.dart',
  'health/presentation/pages/vitals_page.dart',
  'health/presentation/pages/heart_rate_page.dart',
  'health/presentation/pages/health_alerts_page.dart',
  'gate3_health_care_placeholder.dart',
];

void main() {
  test('AppGateRouter product graph is Intro → OtpLogin → Gate3Interactive only',
      () {
    expect(AppGateRouter.buildGatePage(SediAppGate.splash), isA<IntroPage>());
    expect(AppGateRouter.buildGatePage(SediAppGate.login), isA<OtpLoginPage>());
    expect(
      AppGateRouter.buildGatePage(SediAppGate.heart),
      isA<Gate3InteractivePage>(),
    );

    final router = _read('lib/core/navigation/app_gate_router.dart');
    expect(router.contains('IntroPage'), isTrue);
    expect(router.contains('OtpLoginPage'), isTrue);
    expect(router.contains('Gate3InteractivePage'), isTrue);
    expect(router.contains('ChatPage'), isFalse);
    expect(router.contains('OnboardingPage'), isFalse);
    expect(router.contains('UserVerificationPage'), isFalse);
    expect(router.contains('VitalsPage'), isFalse);
    expect(router.contains('HeartRatePage'), isFalse);

    final app = _read('lib/app.dart');
    expect(app.contains('home: const IntroPage()'), isTrue);
    expect(app.contains('SediLocaleController'), isTrue);
    expect(app.contains('SediLocaleRegistry'), isTrue);
    expect(app.contains('AppTheme'), isTrue);
    expect(app.contains('routes:'), isFalse);
    expect(app.contains('onGenerateRoute'), isFalse);
  });

  test('A3 four-icon structure preserved (Profile|Lifestyle|Gadgets|Notifications)',
      () {
    final row = _read(
      'lib/features/gate3_interactive/presentation/widgets/gate3_main_icon_row.dart',
    );
    expect(row.contains('A3 top row: Profile | Lifestyle | Gadgets | Smart Notifications'),
        isTrue);
    expect('Gate3MainIconButton'.allMatches(row).length, 4);
    expect(row.contains('l10n.profileTitle'), isTrue);
    expect(row.contains('l10n.lifestyle'), isTrue);
    expect(row.contains('l10n.gadgets'), isTrue);
    expect(row.contains('l10n.notifications'), isTrue);
    expect(row.contains('Gate3ProfilePage'), isTrue);
    expect(row.contains('onLifestyle'), isTrue);
    expect(row.contains('onGadgets'), isTrue);
    expect(row.contains('onNotifications'), isTrue);
    expect(row.contains('healthCare'), isFalse);
    expect(row.contains('Intelligence'), isFalse);
    expect(row.contains('Icons.favorite'), isFalse);
    expect(row.contains('HeartRatePage'), isFalse);
    expect(row.contains('VitalsPage'), isFalse);
    expect(row.contains('ChatPage'), isFalse);

    final gate3 = _read(
      'lib/features/gate3_interactive/presentation/pages/gate3_interactive_page.dart',
    );
    expect(gate3.contains('LifestylePage'), isTrue);
    expect(gate3.contains('DevicesPage'), isTrue);
    expect(gate3.contains('NotificationInboxPage'), isTrue);
    expect(gate3.contains('ChatPage'), isFalse);
    expect(gate3.contains('VitalsPage'), isFalse);
    expect(gate3.contains('HeartRatePage'), isFalse);
    expect(gate3.contains('OnboardingPage'), isFalse);
  });

  test('canonical Lifestyle Health and Smart Notifications remain reachable', () {
    final lifestyle = _read(
      'lib/features/lifestyle/presentation/pages/lifestyle_page.dart',
    );
    expect(lifestyle.contains('LifestyleHealthPage'), isTrue);
    expect(lifestyle.contains('HeartRatePage'), isFalse);
    expect(lifestyle.contains('VitalsPage'), isFalse);

    final health = _read(
      'lib/features/lifestyle/presentation/pages/lifestyle_health_page.dart',
    );
    expect(health.contains('LifestyleHealthService'), isTrue);
    expect(health.contains('SediLocaleController'), isTrue);

    final inbox = _read(
      'lib/features/notifications/presentation/pages/notification_inbox_page.dart',
    );
    expect(inbox.contains('AppGateRouter.goToHeart'), isTrue);
    expect(inbox.contains('fromNotification: true'), isTrue);
    expect(inbox.contains('ChatPage'), isFalse);

    final bootstrap = _read('lib/core/notifications/notification_bootstrap.dart');
    expect(bootstrap.contains('AppGateRouter.goToHeart'), isTrue);
    expect(bootstrap.contains('fromNotification: true'), isTrue);
    expect(bootstrap.contains('ChatPage'), isFalse);
  });

  test('logout returns through canonical AppGateRouter login', () {
    final auth = _read('lib/core/auth/auth_helper.dart');
    expect(auth.contains('AppGateRouter.goToLogin'), isTrue);
    expect(auth.contains('UserIdentityService.clearCache'), isTrue);
    expect(auth.contains('ChatPage'), isFalse);
    expect(auth.contains('OnboardingPage'), isFalse);

    final profile = _read(
      'lib/features/gate3_interactive/presentation/pages/gate3_profile_page.dart',
    );
    expect(profile.contains('AuthHelper.performLogout'), isTrue);
  });

  test('legacy Chat/Onboarding/UserVerification unreachable from product surfaces',
      () {
    for (final path in _canonicalProductSurfaces) {
      final src = _read(path);
      for (final needle in _legacyPageImportNeedles) {
        expect(
          src.contains(needle),
          isFalse,
          reason: '$path must not import $needle',
        );
      }
      expect(src.contains('ChatPage('), isFalse, reason: path);
      expect(src.contains('OnboardingPage('), isFalse, reason: path);
      expect(src.contains('UserVerificationPage('), isFalse, reason: path);
      expect(src.contains('HeartRatePage('), isFalse, reason: path);
      expect(src.contains('VitalsPage('), isFalse, reason: path);
      expect(src.contains('HealthAlertsPage('), isFalse, reason: path);
    }

    final onboarding = _read(
      'lib/features/onboarding/presentation/pages/onboarding_page.dart',
    );
    expect(onboarding.contains('chat_page.dart'), isFalse);
    expect(onboarding.contains('ChatPage('), isFalse);
    expect(onboarding.contains('AppGateRouter.goToLogin'), isTrue);
    expect(onboarding.contains('UNREACHABLE_LEGACY'), isTrue);

    final chat = _read('lib/features/chat/presentation/pages/chat_page.dart');
    expect(chat.contains('UNREACHABLE_LEGACY'), isTrue);
  });

  test('legacy Health pages unreachable; Gate3HealthCarePlaceholder unused', () {
    final vitals = _read('lib/features/health/presentation/pages/vitals_page.dart');
    expect(vitals.contains('UNREACHABLE_LEGACY'), isTrue);

    final hr = _read('lib/features/health/presentation/pages/heart_rate_page.dart');
    expect(hr.contains('UNREACHABLE_LEGACY'), isTrue);

    final alerts =
        _read('lib/features/health/presentation/pages/health_alerts_page.dart');
    expect(alerts.contains('UNREACHABLE_LEGACY'), isTrue);

    // Placeholder exists but is not imported by any other lib dart file.
    final placeholderPath =
        'lib/features/gate3_interactive/presentation/sections/health_care/gate3_health_care_placeholder.dart';
    expect(_read(placeholderPath).contains('UNREACHABLE_LEGACY'), isTrue);

    final libRoot = Directory('lib');
    final importers = <String>[];
    for (final f in libRoot.listSync(recursive: true)) {
      if (f is! File || !f.path.endsWith('.dart')) continue;
      final normalized = f.path.replaceAll('\\', '/');
      if (normalized.endsWith('gate3_health_care_placeholder.dart')) continue;
      final src = f.readAsStringSync();
      if (src.contains('gate3_health_care_placeholder.dart') ||
          src.contains('Gate3HealthCarePlaceholder')) {
        importers.add(normalized);
      }
    }
    expect(importers, isEmpty);

    // Production Gate3 must not push legacy notification placeholder pages.
    final gate3 = _read(
      'lib/features/gate3_interactive/presentation/pages/gate3_interactive_page.dart',
    );
    expect(gate3.contains('Gate3NotificationsPlaceholder'), isFalse);
    expect(gate3.contains('Gate4NotificationsPlaceholderPage'), isFalse);
    expect(gate3.contains('NotificationsInboxPage'), isFalse);
    expect(gate3.contains('NotificationInboxPage'), isTrue);
  });

  test('gates.dart / app_gate.dart document Gate3InteractivePage authority', () {
    final gates = _read('lib/core/navigation/gates.dart');
    expect(gates.contains('Gate3InteractivePage'), isTrue);
    expect(gates.contains('→ ChatPage'), isFalse);

    final appGate = _read('lib/core/navigation/app_gate.dart');
    expect(appGate.contains('Gate3InteractivePage'), isTrue);
    expect(appGate.contains('ChatPage'), isFalse);
  });
}
