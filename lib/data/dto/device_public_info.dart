/// Device list item including optional HealthSubject binding and G1 classification.
class DevicePublicInfo {
  final String deviceId;
  final String deviceType;
  final String status; // "active" | "revoked" — platform lifecycle, NOT BLE transport
  final DateTime? lastSeenAt;
  final DateTime createdAt;
  final DateTime? revokedAt;
  final int? healthSubjectId;

  /// Backend Device classification: SELF | OTHER | null (legacy unclassified).
  /// Never infer from [healthSubjectId].
  final String? deviceCategory;
  final String? userLabel;

  const DevicePublicInfo({
    required this.deviceId,
    required this.deviceType,
    required this.status,
    this.lastSeenAt,
    required this.createdAt,
    this.revokedAt,
    this.healthSubjectId,
    this.deviceCategory,
    this.userLabel,
  });

  bool get isSelfDevice =>
      (deviceCategory ?? '').trim().toUpperCase() == 'SELF';

  bool get isOtherDevice =>
      (deviceCategory ?? '').trim().toUpperCase() == 'OTHER';

  bool get isUnclassifiedDevice =>
      deviceCategory == null || deviceCategory!.trim().isEmpty;

  /// Friendly presentation name — OTHER prefers userLabel; never clinical.
  String get displayName {
    if (isOtherDevice) {
      final label = userLabel?.trim();
      if (label != null && label.isNotEmpty) return label;
    }
    final type = deviceType.trim();
    if (type.isNotEmpty) return type;
    return deviceId;
  }

  factory DevicePublicInfo.fromJson(Map<String, dynamic> json) {
    DateTime? lastSeenAt;
    if (json['last_seen_at'] != null) {
      if (json['last_seen_at'] is String) {
        lastSeenAt = DateTime.tryParse(json['last_seen_at'] as String);
      } else if (json['last_seen_at'] is DateTime) {
        lastSeenAt = json['last_seen_at'] as DateTime;
      }
    }
    DateTime? createdAt;
    if (json['created_at'] != null) {
      if (json['created_at'] is String) {
        createdAt = DateTime.tryParse(json['created_at'] as String);
      } else if (json['created_at'] is DateTime) {
        createdAt = json['created_at'] as DateTime;
      }
    }
    createdAt ??= DateTime.now();
    DateTime? revokedAt;
    if (json['revoked_at'] != null) {
      if (json['revoked_at'] is String) {
        revokedAt = DateTime.tryParse(json['revoked_at'] as String);
      } else if (json['revoked_at'] is DateTime) {
        revokedAt = json['revoked_at'] as DateTime;
      }
    }
    final rawHs = json['health_subject_id'];
    final rawCategory = json['device_category']?.toString().trim();
    final category = (rawCategory == null || rawCategory.isEmpty)
        ? null
        : rawCategory.toUpperCase();
    final rawLabel = json['user_label']?.toString();
    final label = rawLabel == null ? null : rawLabel.trim();
    return DevicePublicInfo(
      deviceId: json['device_id']?.toString() ?? '',
      deviceType: json['device_type']?.toString() ?? 'heart_rate',
      status: json['status']?.toString() ?? 'active',
      lastSeenAt: lastSeenAt,
      createdAt: createdAt,
      revokedAt: revokedAt,
      healthSubjectId: rawHs is int ? rawHs : int.tryParse('$rawHs'),
      deviceCategory: category,
      userLabel: (label == null || label.isEmpty) ? null : label,
    );
  }
}
