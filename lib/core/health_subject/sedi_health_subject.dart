/// Canonical A3 HealthSubject snapshot from GET /health-subjects.
class SediHealthSubject {
  final int id;
  final String? displayName;
  final String subjectKind; // self | managed | legacy_user
  final String status;
  final String? accessRole; // SELF | CAREGIVER | MANAGER
  final int? linkedUserId;

  const SediHealthSubject({
    required this.id,
    this.displayName,
    required this.subjectKind,
    required this.status,
    this.accessRole,
    this.linkedUserId,
  });

  bool get isSelf =>
      subjectKind == 'self' || (accessRole ?? '').toUpperCase() == 'SELF';

  String get visibleName {
    final n = (displayName ?? '').trim();
    if (n.isNotEmpty) return n;
    return isSelf ? 'Me' : 'Person #$id';
  }

  factory SediHealthSubject.fromJson(Map<String, dynamic> json) {
    final rawId = json['health_subject_id'] ?? json['id'];
    return SediHealthSubject(
      id: rawId is int ? rawId : int.tryParse('$rawId') ?? 0,
      displayName: json['display_name']?.toString(),
      subjectKind: (json['subject_kind'] ?? 'managed').toString(),
      status: (json['status'] ?? 'active').toString(),
      accessRole: json['access_role']?.toString(),
      linkedUserId: json['linked_user_id'] is int
          ? json['linked_user_id'] as int
          : int.tryParse('${json['linked_user_id'] ?? ''}'),
    );
  }
}
