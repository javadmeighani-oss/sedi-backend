/// Devices list and register logic. JWT via DevicesRepository; no profile userId.
import '../../../data/dto/device_public_info.dart';
import '../../../data/dto/device_register_request.dart';
import '../../../data/repositories/devices_repository.dart';

class DevicesController {
  final DevicesRepository _repo;

  DevicesController({DevicesRepository? repo})
      : _repo = repo ?? DevicesRepository();

  bool isLoading = false;
  bool isActionInProgress = false;
  List<DevicePublicInfo> devices = [];
  String? errorMessage;

  /// Devices with backend device_category=SELF only.
  List<DevicePublicInfo> get selfDevices =>
      devices.where((d) => d.isSelfDevice).toList(growable: false);

  /// Devices with backend device_category=OTHER only.
  List<DevicePublicInfo> get otherDevices =>
      devices.where((d) => d.isOtherDevice).toList(growable: false);

  /// Legacy rows with null/empty category — never inferred as OTHER/SELF.
  List<DevicePublicInfo> get unclassifiedDevices =>
      devices.where((d) => d.isUnclassifiedDevice).toList(growable: false);

  /// Load devices for authenticated Account. Clears error on success.
  Future<void> loadDevices() async {
    isLoading = true;
    errorMessage = null;
    try {
      final response = await _repo.list();
      if (response.ok && response.data != null) {
        devices = response.data!.devices;
        errorMessage = null;
      } else {
        errorMessage = response.errorMessage;
      }
    } catch (e) {
      errorMessage = e.toString();
    } finally {
      isLoading = false;
    }
  }

  /// Register a device. On success reloads list; on failure sets errorMessage.
  Future<bool> registerDevice(String deviceId, [String? deviceType]) async {
    if (isActionInProgress) {
      errorMessage = 'Please wait.';
      return false;
    }
    final trimmed = deviceId.trim();
    if (trimmed.isEmpty) {
      errorMessage = 'Device ID is required';
      return false;
    }
    isActionInProgress = true;
    errorMessage = null;
    try {
      final request = DeviceRegisterRequest(
        deviceId: trimmed,
        deviceType:
            deviceType?.trim().isEmpty == true ? null : deviceType?.trim(),
      );
      final response = await _repo.register(request: request);
      if (!response.ok) {
        errorMessage = response.errorMessage;
        return false;
      }
      await loadDevices();
      return true;
    } finally {
      isActionInProgress = false;
    }
  }

  /// Revoke a device. On success reloads list.
  Future<bool> revokeDevice(String deviceId) async {
    if (isActionInProgress) {
      errorMessage = 'Please wait.';
      return false;
    }
    isActionInProgress = true;
    errorMessage = null;
    try {
      final response = await _repo.revoke(deviceId: deviceId);
      if (!response.ok) {
        errorMessage = response.errorMessage;
        return false;
      }
      await loadDevices();
      return true;
    } finally {
      isActionInProgress = false;
    }
  }

  /// Rotate device token. On success reloads list.
  Future<bool> rotateDeviceToken(String deviceId) async {
    if (isActionInProgress) {
      errorMessage = 'Please wait.';
      return false;
    }
    isActionInProgress = true;
    errorMessage = null;
    try {
      final response = await _repo.rotateToken(deviceId: deviceId);
      if (!response.ok) {
        errorMessage = response.errorMessage;
        return false;
      }
      await loadDevices();
      return true;
    } finally {
      isActionInProgress = false;
    }
  }

  /// Owner presentation update (category + optional label). Reloads on success.
  Future<bool> updateDevicePresentation({
    required String deviceId,
    required String deviceCategory,
    String? userLabel,
  }) async {
    if (isActionInProgress) {
      errorMessage = 'Please wait.';
      return false;
    }
    final category = deviceCategory.trim().toUpperCase();
    if (category != 'SELF' && category != 'OTHER') {
      errorMessage = 'Invalid device category';
      return false;
    }
    final trimmedLabel = userLabel?.trim();
    if (category == 'OTHER' &&
        (trimmedLabel == null || trimmedLabel.isEmpty)) {
      errorMessage = 'Label required for OTHER devices';
      return false;
    }
    if (trimmedLabel != null && trimmedLabel.length > 80) {
      errorMessage = 'Label max length is 80';
      return false;
    }
    isActionInProgress = true;
    errorMessage = null;
    try {
      final response = await _repo.updatePresentation(
        deviceId: deviceId,
        deviceCategory: category,
        userLabel: category == 'OTHER'
            ? trimmedLabel
            : (trimmedLabel == null || trimmedLabel.isEmpty
                ? null
                : trimmedLabel),
      );
      if (!response.ok) {
        errorMessage = response.errorMessage;
        return false;
      }
      await loadDevices();
      return true;
    } finally {
      isActionInProgress = false;
    }
  }
}

// --- UI-friendly mapping (for tests and UI) ---

/// Status label for device card: Active / Revoked (lifecycle — not BLE Connected).
String deviceStatusLabel(String status) {
  final s = (status).toLowerCase();
  if (s == 'revoked') return 'Revoked';
  return 'Active';
}

/// Last seen label: formatted date-time or "Never".
String deviceLastSeenLabel(DateTime? lastSeenAt) {
  if (lastSeenAt == null) return 'Never';
  final n = DateTime.now();
  final d = lastSeenAt;
  if (d.year == n.year && d.month == n.month && d.day == n.day) {
    return '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
  }
  return '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
}
