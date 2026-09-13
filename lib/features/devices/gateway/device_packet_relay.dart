import '../../core/network/api_client.dart';
import '../../core/network/api_response.dart';
import '../../data/repositories/devices_repository.dart';
import '../ble/sedi_ble_models.dart';
import 'device_packet_mapper.dart';
import 'durable_packet_outbox.dart';
import 'gateway_install_id_store.dart';

enum PacketRelayAck {
  accepted,
  duplicate,
  recoverableFailure,
  permanentFailure,
}

class PacketRelayResult {
  final PacketRelayAck ack;
  final String? message;
  final String clientPacketId;

  const PacketRelayResult({
    required this.ack,
    required this.clientPacketId,
    this.message,
  });
}

/// Secure mobile gateway → canonical I9 POST /device/packet with durable outbox.
class DevicePacketRelay {
  DevicePacketRelay({
    required DevicesRepository devicesRepository,
    required DurablePacketOutbox outbox,
    required GatewayInstallIdStore gatewayInstallIdStore,
    ApiClient? apiClient,
  })  : _repo = devicesRepository,
        _outbox = outbox,
        _gatewayStore = gatewayInstallIdStore;

  final DevicesRepository _repo;
  final DurablePacketOutbox _outbox;
  final GatewayInstallIdStore _gatewayStore;

  static const permanentAckCodes = {
    'AUTH_FAILURE',
    'REJECTED_REVOKED',
    'REJECTED_GATEWAY',
    'GATEWAY_AUTH_REQUIRED',
    'GATEWAY_AUTH_REJECTED',
    'GATEWAY_REVOKED',
    'GATEWAY_MISMATCH',
    'VALIDATION_ERROR',
    'REJECTED',
    'REJECTED_NO_BINDING',
  };

  /// Enqueue then attempt send. [clientPacketId] stable across retries.
  Future<PacketRelayResult> enqueueAndRelay({
    required String deviceId,
    required String deviceToken,
    required SediBleDeviceData data,
    String? firmwareVersion,
  }) async {
    final gatewayInstallId = await _gatewayStore.getOrCreate();
    final body = DevicePacketMapper.toPacketBody(
      data: data,
      gatewayInstallId: gatewayInstallId,
      firmwareVersion: firmwareVersion,
    );
    final entry = OutboxEntry(
      deviceId: deviceId,
      clientPacketId: data.packetId,
      measuredAtIso: data.measuredAt.toUtc().toIso8601String(),
      gatewayInstallId: gatewayInstallId,
      packetBody: body,
      enqueuedAt: DateTime.now().toUtc(),
    );
    final accepted = await _outbox.enqueue(entry);
    if (!accepted) {
      return PacketRelayResult(
        ack: PacketRelayAck.permanentFailure,
        clientPacketId: data.packetId,
        message: 'OUTBOX_FULL',
      );
    }
    return _sendEntry(entry, deviceToken: deviceToken);
  }

  Future<List<PacketRelayResult>> flushPending({
    required String deviceId,
    required String deviceToken,
  }) async {
    final results = <PacketRelayResult>[];
    final all = await _outbox.peekAll();
    for (final entry in all) {
      if (entry.deviceId != deviceId) continue;
      if (entry.permanentFailure) continue;
      results.add(await _sendEntry(entry, deviceToken: deviceToken));
    }
    await _outbox.dropPermanentFailures();
    return results;
  }

  Future<PacketRelayResult> _sendEntry(
    OutboxEntry entry, {
    required String deviceToken,
  }) async {
    final clientPacketId = entry.clientPacketId;
    try {
      final resp = await _repo.postDevicePacket(
        deviceToken: deviceToken,
        body: entry.packetBody,
      );
      final ack = _classify(resp);
      if (ack == PacketRelayAck.accepted || ack == PacketRelayAck.duplicate) {
        await _outbox.remove(
          deviceId: entry.deviceId,
          clientPacketId: clientPacketId,
        );
      } else if (ack == PacketRelayAck.permanentFailure) {
        await _outbox.markPermanentFailure(
          deviceId: entry.deviceId,
          clientPacketId: clientPacketId,
          reason: resp.error?.code ?? 'PERMANENT',
        );
      }
      return PacketRelayResult(
        ack: ack,
        clientPacketId: clientPacketId,
        message: resp.error?.message ?? resp.error?.code,
      );
    } catch (e) {
      return PacketRelayResult(
        ack: PacketRelayAck.recoverableFailure,
        clientPacketId: clientPacketId,
        message: e.toString(),
      );
    }
  }

  PacketRelayAck _classify(ApiResponse<Map<String, dynamic>?> resp) {
    final data = resp.data;
    final ackStatus = data?['ack_status']?.toString().toUpperCase();
    if (resp.ok) {
      if (ackStatus == 'DUPLICATE') return PacketRelayAck.duplicate;
      return PacketRelayAck.accepted;
    }
    final code = (resp.error?.code ?? ackStatus ?? '').toUpperCase();
    if (permanentAckCodes.contains(code) ||
        code.startsWith('GATEWAY_') ||
        code.startsWith('REJECTED')) {
      return PacketRelayAck.permanentFailure;
    }
    return PacketRelayAck.recoverableFailure;
  }
}
