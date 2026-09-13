/// Devices management: JWT-authenticated Account Device control-plane.
/// Canonical identity = ApiClient session; never send ?user_id=.
import '../../core/config/app_config.dart';
import '../../core/network/api_client.dart';
import '../../core/network/api_response.dart';
import '../dto/device_register_request.dart';
import '../dto/devices_list_response.dart';

class DevicesRepository {
  final ApiClient _client;

  DevicesRepository({String? baseUrl, ApiClient? apiClient})
      : _client = apiClient ?? ApiClient(baseUrl: baseUrl ?? AppConfig.baseUrl);

  /// POST /devices/register — register device for authenticated Account.
  Future<ApiResponse<Map<String, dynamic>?>> register({
    required DeviceRegisterRequest request,
  }) async {
    return _client.post<Map<String, dynamic>?>(
      '/devices/register',
      body: request.toJson(),
      parser: (v) => v == null ? null : Map<String, dynamic>.from(v as Map),
    );
  }

  /// GET /devices — list devices for authenticated Account.
  Future<ApiResponse<DevicesListData?>> list() async {
    return _client.get<DevicesListData?>(
      '/devices',
      parser: (v) {
        if (v == null) return null;
        final map = v is Map ? Map<String, dynamic>.from(v) : null;
        return map != null ? DevicesListData.fromJson(map) : null;
      },
    );
  }

  /// POST /devices/{device_id}/revoke — revoke device.
  Future<ApiResponse<Map<String, dynamic>?>> revoke({
    required String deviceId,
  }) async {
    return _client.post<Map<String, dynamic>?>(
      '/devices/$deviceId/revoke',
      parser: (v) => v == null ? null : Map<String, dynamic>.from(v as Map),
    );
  }

  /// POST /devices/{device_id}/rotate-token — rotate device token.
  Future<ApiResponse<Map<String, dynamic>?>> rotateToken({
    required String deviceId,
  }) async {
    return _client.post<Map<String, dynamic>?>(
      '/devices/$deviceId/rotate-token',
      parser: (v) => v == null ? null : Map<String, dynamic>.from(v as Map),
    );
  }

  /// PATCH /devices/{device_id} — owner presentation only (category + label).
  Future<ApiResponse<Map<String, dynamic>?>> updatePresentation({
    required String deviceId,
    required String deviceCategory,
    String? userLabel,
  }) async {
    final body = <String, dynamic>{
      'device_category': deviceCategory.trim().toUpperCase(),
      'user_label': userLabel,
    };
    return _client.patch<Map<String, dynamic>?>(
      '/devices/$deviceId',
      body: body,
      parser: (v) => v == null ? null : Map<String, dynamic>.from(v as Map),
    );
  }

  /// POST /devices/{device_id}/gateway/pair — reuse governed gateway lifecycle.
  Future<ApiResponse<Map<String, dynamic>?>> pairGateway({
    required String deviceId,
    required String gatewayInstallId,
  }) async {
    return _client.post<Map<String, dynamic>?>(
      '/devices/$deviceId/gateway/pair',
      body: {'gateway_install_id': gatewayInstallId},
      parser: (v) => v == null ? null : Map<String, dynamic>.from(v as Map),
    );
  }

  /// POST /devices/{device_id}/gateway/disconnect — revoke mobile gateway auth.
  Future<ApiResponse<Map<String, dynamic>?>> disconnectGateway({
    required String deviceId,
    required String gatewayInstallId,
  }) async {
    return _client.post<Map<String, dynamic>?>(
      '/devices/$deviceId/gateway/disconnect',
      body: {'gateway_install_id': gatewayInstallId},
      parser: (v) => v == null ? null : Map<String, dynamic>.from(v as Map),
    );
  }

  /// Canonical I9 ingest only: POST /device/packet (never /device/ingest or /data/upload).
  Future<ApiResponse<Map<String, dynamic>?>> postDevicePacket({
    required String deviceToken,
    required Map<String, dynamic> body,
  }) async {
    return _client.post<Map<String, dynamic>?>(
      '/device/packet',
      body: body,
      extraHeaders: {'X-DEVICE-TOKEN': deviceToken},
      parser: (v) => v == null ? null : Map<String, dynamic>.from(v as Map),
    );
  }
}
