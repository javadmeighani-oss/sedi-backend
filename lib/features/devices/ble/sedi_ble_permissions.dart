import 'dart:io' show Platform;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/services.dart';

/// Outcome of a Sedi Gadget BLE runtime permission request.
enum SediBlePermissionOutcome {
  granted,
  denied,
  permanentlyDenied,
}

typedef BlePermissionPlatformInvoker = Future<String> Function();
typedef OpenAppSettingsInvoker = Future<bool> Function();

/// Real Android BLE runtime permission for Gadgets scan/connect.
///
/// Uses a bounded MethodChannel (`sedi/ble_permissions`) — no extra pub
/// dependency (compileSdk 34 / minSdk 23 compatible).
///
/// Android 12+ (API 31+): BLUETOOTH_SCAN + BLUETOOTH_CONNECT.
/// Android ≤30: ACCESS_FINE_LOCATION only (legacy BLE scan gate).
///
/// Production must not use a default `() async => true` bypass.
class SediBlePermissions {
  SediBlePermissions._();

  static const MethodChannel _channel = MethodChannel('sedi/ble_permissions');

  /// Last outcome (for UI messaging / settings path).
  static SediBlePermissionOutcome lastOutcome =
      SediBlePermissionOutcome.granted;

  /// Production requester for [GadgetsConnectController].
  static Future<bool> request({
    BlePermissionPlatformInvoker? invokePlatform,
    OpenAppSettingsInvoker? openSettings,
    bool? isAndroidOverride,
  }) async {
    final outcome = await requestDetailed(
      invokePlatform: invokePlatform,
      openSettings: openSettings,
      isAndroidOverride: isAndroidOverride,
    );
    return outcome == SediBlePermissionOutcome.granted;
  }

  static Future<SediBlePermissionOutcome> requestDetailed({
    BlePermissionPlatformInvoker? invokePlatform,
    OpenAppSettingsInvoker? openSettings,
    bool? isAndroidOverride,
  }) async {
    final isAndroid = isAndroidOverride ?? (!kIsWeb && Platform.isAndroid);
    if (!isAndroid) {
      lastOutcome = SediBlePermissionOutcome.granted;
      return lastOutcome;
    }

    final invoker = invokePlatform ??
        () async {
          final raw =
              await _channel.invokeMethod<String>('requestBlePermissions');
          return raw ?? 'denied';
        };

    final raw = (await invoker()).trim();
    switch (raw) {
      case 'granted':
        lastOutcome = SediBlePermissionOutcome.granted;
        return lastOutcome;
      case 'permanentlyDenied':
        lastOutcome = SediBlePermissionOutcome.permanentlyDenied;
        final open = openSettings ??
            () async {
              final ok =
                  await _channel.invokeMethod<bool>('openAppSettings');
              return ok ?? false;
            };
        await open();
        return lastOutcome;
      default:
        lastOutcome = SediBlePermissionOutcome.denied;
        return lastOutcome;
    }
  }
}
