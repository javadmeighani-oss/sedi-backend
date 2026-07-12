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

    final summaryFuture = _repo.fetchLifestyleSummary(lang: lang);
    final contextFuture = _repo.fetchLifestyleContext();
    final habitsFuture = _repo.fetchHabits();
    final goalsFuture = _repo.fetchGoals();
    final restrictionsFuture = _repo.fetchRestrictions();
    final eventsFuture = _repo.fetchEvents();
    final lifestyleEventsFuture = _repo.fetchLifestyleEvents();
    final carePlanFuture = _repo.fetchCarePlanItems();

    final summaryRes = await summaryFuture;
    final contextRes = await contextFuture;
    final habitsRes = await habitsFuture;
    final goalsRes = await goalsFuture;
    final restrictionsRes = await restrictionsFuture;
    final eventsRes = await eventsFuture;
    final lifestyleEventsRes = await lifestyleEventsFuture;
    final carePlanRes = await carePlanFuture;

    if (summaryRes.ok && summaryRes.data != null) {
      summarySections = summaryRes.data!.sections
          .map((s) => {
                'title': s.title,
                'body': s.body,
                'items': s.items,
              })
          .toList();
    }

    if (contextRes.ok && contextRes.data != null) {
      lifestyleContext = contextRes.data;
    }

    if (habitsRes.ok) habits = habitsRes.data ?? habits;
    if (goalsRes.ok) goals = goalsRes.data ?? goals;
    if (restrictionsRes.ok) restrictions = restrictionsRes.data ?? restrictions;
    if (eventsRes.ok) events = eventsRes.data ?? events;
    if (lifestyleEventsRes.ok) {
      lifestyleEvents = lifestyleEventsRes.data ?? lifestyleEvents;
    }
    if (carePlanRes.ok) carePlanItems = carePlanRes.data ?? carePlanItems;

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
