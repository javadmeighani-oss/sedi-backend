/// Presentation DTO for existing I6 GET/POST /memory/consent payloads.
class MemoryConsentStatus {
  const MemoryConsentStatus({
    required this.granted,
    required this.status,
    required this.writeAllowed,
    required this.readAllowed,
    required this.forgetAllowed,
    this.policyVersion,
  });

  final bool granted;
  final String status;
  final bool writeAllowed;
  final bool readAllowed;
  final bool forgetAllowed;
  final String? policyVersion;

  static MemoryConsentStatus? tryParse(Object? data) {
    if (data is! Map) return null;
    final map = Map<String, dynamic>.from(data);
    final granted = map['granted'] == true;
    final status = (map['status']?.toString() ?? '').trim();
    final permsRaw = map['permissions'];
    final perms = permsRaw is Map
        ? Map<String, dynamic>.from(permsRaw)
        : const <String, dynamic>{};
    return MemoryConsentStatus(
      granted: granted,
      status: status.isEmpty ? (granted ? 'active' : 'none') : status,
      writeAllowed: perms['memory.write'] == true,
      readAllowed: perms['memory.read'] == true,
      forgetAllowed: perms['memory.forget'] == true,
      policyVersion: map['policy_version']?.toString(),
    );
  }
}
