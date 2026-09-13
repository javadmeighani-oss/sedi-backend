/// Debug helper: register device + list devices (JWT via DevicesRepository).
/// Guarded — call explicitly; not executed automatically.
import '../../data/dto/device_register_request.dart';
import '../../data/repositories/devices_repository.dart';

/// Registers a sample device and then lists devices for the authenticated Account.
Future<String> smokeDevices() async {
  final repo = DevicesRepository();
  final req =
      DeviceRegisterRequest(deviceId: 'SediDebug001', deviceType: 'heart_rate');
  final registerResp = await repo.register(request: req);
  if (!registerResp.ok) {
    return '[smoke_devices] register FAIL ${registerResp.error?.message ?? "unknown"}';
  }
  final listResp = await repo.list();
  if (!listResp.ok || listResp.data == null) {
    return '[smoke_devices] register OK; list FAIL ${listResp.error?.message ?? "no data"}';
  }
  return '[smoke_devices] OK registered; list count=${listResp.data!.count}';
}
