import 'package:flutter/foundation.dart';

import '../network/api_client.dart';
import 'sedi_health_subject.dart';

/// Canonical A3 selected HealthSubject authority (presentation only — not authorization).
class SediHealthSubjectController extends ChangeNotifier {
  SediHealthSubjectController._();
  static final SediHealthSubjectController instance =
      SediHealthSubjectController._();

  final ApiClient _api = ApiClient();

  List<SediHealthSubject> accessibleSubjects = const [];
  SediHealthSubject? selfSubject;
  SediHealthSubject? activeSubject;
  int generation = 0;
  bool loading = false;
  String? error;

  Future<void> loadAccessibleSubjects() async {
    loading = true;
    error = null;
    notifyListeners();
    final res = await _api.get<List<SediHealthSubject>>(
      '/health-subjects',
      parser: (data) {
        if (data is! Map) return <SediHealthSubject>[];
        final raw = data['health_subjects'];
        if (raw is! List) return <SediHealthSubject>[];
        return raw
            .whereType<Map>()
            .map((e) => SediHealthSubject.fromJson(Map<String, dynamic>.from(e)))
            .where((s) => s.id > 0)
            .toList();
      },
    );
    loading = false;
    if (!res.ok || res.data == null) {
      error = res.errorMessage;
      accessibleSubjects = const [];
      selfSubject = null;
      activeSubject = null;
      generation++;
      notifyListeners();
      return;
    }
    accessibleSubjects = res.data!;
    SediHealthSubject? self;
    for (final s in accessibleSubjects) {
      if (s.isSelf) {
        self = s;
        break;
      }
    }
    selfSubject = self;
    activeSubject = selfSubject ??
        (accessibleSubjects.isEmpty ? null : accessibleSubjects.first);
    generation++;
    notifyListeners();
  }

  /// Switch active subject; bumps [generation] so consumers invalidate caches.
  void selectSubject(int healthSubjectId) {
    SediHealthSubject? next;
    for (final s in accessibleSubjects) {
      if (s.id == healthSubjectId) {
        next = s;
        break;
      }
    }
    if (next == null) return;
    if (activeSubject?.id == next.id) return;
    activeSubject = next;
    generation++;
    notifyListeners();
  }

  bool get isActiveSelf => activeSubject?.isSelf ?? true;

  /// Clears presentation subject state on logout / invalid-session end.
  /// Does not invent subjects; next A3 must reload from backend.
  void clearSessionState() {
    accessibleSubjects = const [];
    selfSubject = null;
    activeSubject = null;
    generation++;
    loading = false;
    error = null;
    notifyListeners();
  }

  @visibleForTesting
  void debugResetForTest() {
    accessibleSubjects = const [];
    selfSubject = null;
    activeSubject = null;
    generation = 0;
    loading = false;
    error = null;
  }

  @visibleForTesting
  void debugSeedForTest({
    required List<SediHealthSubject> subjects,
    int? activeId,
  }) {
    accessibleSubjects = subjects;
    SediHealthSubject? self;
    for (final s in subjects) {
      if (s.isSelf) {
        self = s;
        break;
      }
    }
    selfSubject = self;
    SediHealthSubject? active = self;
    if (activeId != null) {
      for (final s in subjects) {
        if (s.id == activeId) {
          active = s;
          break;
        }
      }
    }
    activeSubject = active ?? (subjects.isEmpty ? null : subjects.first);
    generation++;
  }
}
