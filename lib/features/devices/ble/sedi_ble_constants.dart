/// Frozen Sedi Gadget BLE GATT UUID authority (protocol v1).
/// Single source — do not duplicate UUIDs elsewhere.
library;

class SediBleConstants {
  SediBleConstants._();

  static const int protocolVersion = 1;

  static const String primaryServiceUuid =
      'f2e6981f-4dc1-526d-a2c8-a043a1cddfa5';

  static const String deviceInfoUuid =
      '467febf0-6629-59ed-a748-009d244af686';

  static const String claimChallengeUuid =
      '3a8d703c-ac28-58b4-8eaa-84ac990fae71';

  static const String claimProofUuid =
      '4d2c701d-1d1d-5a72-a961-e8d23fe9dfa0';

  static const String deviceDataUuid =
      'f144aeda-24e5-56df-a132-2e428b0dc1c2';

  static const String deviceStatusUuid =
      '46b5efee-7522-5e4a-abbf-4d391478109b';

  static const String deviceControlUuid =
      '82db957c-b074-5e7b-b484-23fc0165aee1';

  /// DEVICE_REPORTED only — mobile never invents clinical stability.
  static const String sourceClassDeviceReported = 'DEVICE_REPORTED';

  static const String deviceIdPattern =
      r'^SEDI-[A-Z0-9]+-\d{12}$';

  static const String setupCodePattern = r'^\d{4}$';
}
