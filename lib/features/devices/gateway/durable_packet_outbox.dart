import 'dart:convert';
import 'dart:io';

/// Bounded durable outbox for canonical JSON packet payloads only.
/// No raw ECG waveform storage.
///
/// When full: fail-visible — rejects enqueue of newest packet (oldest retained).
/// Max [maxEntries] (default 64).
class DurablePacketOutbox {
  DurablePacketOutbox({
    required this.file,
    this.maxEntries = 64,
  });

  final File file;
  final int maxEntries;

  static const maxEntriesDefault = 64;

  List<OutboxEntry> _entries = [];
  bool _loaded = false;

  Future<void> ensureLoaded() async {
    if (_loaded) return;
    if (!await file.exists()) {
      _entries = [];
      _loaded = true;
      return;
    }
    try {
      final text = await file.readAsString();
      if (text.trim().isEmpty) {
        _entries = [];
      } else {
        final decoded = jsonDecode(text);
        if (decoded is List) {
          _entries = decoded
              .whereType<Map>()
              .map((m) => OutboxEntry.fromJson(Map<String, dynamic>.from(m)))
              .toList();
        } else {
          _entries = [];
        }
      }
    } catch (_) {
      _entries = [];
    }
    _loaded = true;
  }

  Future<void> _persist() async {
    await file.parent.create(recursive: true);
    final encoded = jsonEncode(_entries.map((e) => e.toJson()).toList());
    await file.writeAsString(encoded, flush: true);
  }

  /// Enqueue BEFORE network send. Returns false if queue full (fail-visible).
  Future<bool> enqueue(OutboxEntry entry) async {
    await ensureLoaded();
    if (_entries.any((e) =>
        e.deviceId == entry.deviceId &&
        e.clientPacketId == entry.clientPacketId)) {
      // Same identity already queued — keep existing (stable packet id).
      return true;
    }
    if (_entries.length >= maxEntries) {
      return false;
    }
    _entries.add(entry);
    await _persist();
    return true;
  }

  Future<List<OutboxEntry>> peekAll() async {
    await ensureLoaded();
    return List.unmodifiable(_entries);
  }

  Future<OutboxEntry?> peekNext() async {
    await ensureLoaded();
    if (_entries.isEmpty) return null;
    return _entries.first;
  }

  Future<void> remove({
    required String deviceId,
    required String clientPacketId,
  }) async {
    await ensureLoaded();
    _entries.removeWhere(
      (e) => e.deviceId == deviceId && e.clientPacketId == clientPacketId,
    );
    await _persist();
  }

  Future<void> markPermanentFailure({
    required String deviceId,
    required String clientPacketId,
    required String reason,
  }) async {
    await ensureLoaded();
    final idx = _entries.indexWhere(
      (e) => e.deviceId == deviceId && e.clientPacketId == clientPacketId,
    );
    if (idx < 0) return;
    _entries[idx] = _entries[idx].copyWith(
      permanentFailure: true,
      failureReason: reason,
    );
    await _persist();
  }

  Future<void> dropPermanentFailures() async {
    await ensureLoaded();
    _entries.removeWhere((e) => e.permanentFailure);
    await _persist();
  }

  int get length => _entries.length;
}

class OutboxEntry {
  final String deviceId;
  final String clientPacketId;
  final String measuredAtIso;
  final String gatewayInstallId;
  final Map<String, dynamic> packetBody;
  final bool permanentFailure;
  final String? failureReason;
  final DateTime enqueuedAt;

  const OutboxEntry({
    required this.deviceId,
    required this.clientPacketId,
    required this.measuredAtIso,
    required this.gatewayInstallId,
    required this.packetBody,
    this.permanentFailure = false,
    this.failureReason,
    required this.enqueuedAt,
  });

  OutboxEntry copyWith({
    bool? permanentFailure,
    String? failureReason,
  }) {
    return OutboxEntry(
      deviceId: deviceId,
      clientPacketId: clientPacketId,
      measuredAtIso: measuredAtIso,
      gatewayInstallId: gatewayInstallId,
      packetBody: packetBody,
      permanentFailure: permanentFailure ?? this.permanentFailure,
      failureReason: failureReason ?? this.failureReason,
      enqueuedAt: enqueuedAt,
    );
  }

  Map<String, dynamic> toJson() => {
        'device_id': deviceId,
        'client_packet_id': clientPacketId,
        'measured_at': measuredAtIso,
        'gateway_install_id': gatewayInstallId,
        'packet_body': packetBody,
        'permanent_failure': permanentFailure,
        if (failureReason != null) 'failure_reason': failureReason,
        'enqueued_at': enqueuedAt.toUtc().toIso8601String(),
      };

  factory OutboxEntry.fromJson(Map<String, dynamic> json) {
    return OutboxEntry(
      deviceId: (json['device_id'] ?? '').toString(),
      clientPacketId: (json['client_packet_id'] ?? '').toString(),
      measuredAtIso: (json['measured_at'] ?? '').toString(),
      gatewayInstallId: (json['gateway_install_id'] ?? '').toString(),
      packetBody: json['packet_body'] is Map
          ? Map<String, dynamic>.from(json['packet_body'] as Map)
          : <String, dynamic>{},
      permanentFailure: json['permanent_failure'] == true,
      failureReason: json['failure_reason']?.toString(),
      enqueuedAt: DateTime.tryParse(json['enqueued_at']?.toString() ?? '')
              ?.toUtc() ??
          DateTime.now().toUtc(),
    );
  }
}
