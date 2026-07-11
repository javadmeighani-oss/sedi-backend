import 'package:flutter/foundation.dart';

import '../../../data/repositories/gate3_user_data_repository.dart';
import '../presentation/gate3_sections_localization.dart';

class LifestyleSectionController extends ChangeNotifier {
  final Gate3UserDataRepository _repo;
  final String lang;

  LifestyleSectionController({
    required this.lang,
    Gate3UserDataRepository? repository,
  }) : _repo = repository ?? Gate3UserDataRepository();

  bool loading = false;
  bool refreshing = false;
  String? error;
  Map<String, dynamic>? lifestyleContext;
  List<dynamic> summarySections = [];
  List<Map<String, dynamic>> habits = [];
  List<Map<String, dynamic>> goals = [];
  List<Map<String, dynamic>> restrictions = [];
  List<Map<String, dynamic>> events = [];
  List<Map<String, dynamic>> lifestyleEvents = [];
  List<Map<String, dynamic>> carePlanItems = [];
  DateTime? lastLoadedAt;

  Gate3SectionsLocalization get l10n => Gate3SectionsLocalization(lang);

  Future<void> load({bool isRefresh = false}) async {
    if (loading && !isRefresh) return;
    if (isRefresh) {
      refreshing = true;
    } else {
      loading = true;
    }
    error = null;
    notifyListeners();

    final results = await Future.wait([
      _repo.fetchLifestyleSummary(lang: lang),
      _repo.fetchLifestyleContext(),
      _repo.fetchHabits(),
      _repo.fetchGoals(),
      _repo.fetchRestrictions(),
      _repo.fetchEvents(),
      _repo.fetchLifestyleEvents(),
      _repo.fetchCarePlanItems(),
    ]);

    final summaryRes = results[0];
    if (summaryRes.ok && summaryRes.data != null) {
      summarySections = summaryRes.data!.sections
          .map((s) => {
                'title': s.title,
                'body': s.body,
                'items': s.items,
              })
          .toList();
    }

    if (results[1].ok && results[1].data != null) {
      lifestyleContext = results[1].data;
    }

    if (results[2].ok) habits = results[2].data ?? habits;
    if (results[3].ok) goals = results[3].data ?? goals;
    if (results[4].ok) restrictions = results[4].data ?? restrictions;
    if (results[5].ok) events = results[5].data ?? events;
    if (results[6].ok) lifestyleEvents = results[6].data ?? lifestyleEvents;
    if (results[7].ok) carePlanItems = results[7].data ?? carePlanItems;

    if (!summaryRes.ok &&
        lifestyleContext == null &&
        habits.isEmpty &&
        goals.isEmpty) {
      error = l10n.genericError();
    }

    lastLoadedAt = DateTime.now();
    loading = false;
    refreshing = false;
    notifyListeners();
  }

  List<Map<String, dynamic>> get lifestyleDomainEvents {
    return events.where((e) {
      final domain = e['event_domain']?.toString() ?? '';
      return domain == 'lifestyle' || domain == 'wellness';
    }).toList();
  }

  List<Map<String, dynamic>> get weeklyPlanItems {
    final fromGoals = goals.where((g) {
      final cat = g['category']?.toString() ?? '';
      final freq = g['target_json']?.toString() ?? '';
      return cat.contains('weekly') || freq.contains('weekly');
    }).toList();
    if (fromGoals.isNotEmpty) return fromGoals;
    return carePlanItems.where((c) {
      final cat = c['category']?.toString() ?? '';
      return cat.contains('weekly');
    }).toList();
  }
}
