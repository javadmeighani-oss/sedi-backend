import 'package:flutter/foundation.dart';

import '../../../data/repositories/gate3_gadgets_repository.dart';
import '../presentation/gate3_sections_localization.dart';

class GadgetsSectionController extends ChangeNotifier {
  final Gate3GadgetsRepository _repo;
  final String lang;

  GadgetsSectionController({
    required this.lang,
    Gate3GadgetsRepository? repository,
  }) : _repo = repository ?? Gate3GadgetsRepository();

  bool loading = false;
  bool refreshing = false;
  String? error;
  Map<String, dynamic>? hubStatus;
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

    final res = await _repo.fetchHubStatus();
    if (!res.ok) {
      if (hubStatus == null) error = l10n.genericError();
    } else {
      hubStatus = res.data;
    }

    lastLoadedAt = DateTime.now();
    loading = false;
    refreshing = false;
    notifyListeners();
  }

  bool get hasHub => hubStatus?['has_hub'] == true;

  String get operationalStatus =>
      hubStatus?['status']?.toString() ?? 'unknown';

  Map<String, dynamic>? get hub => hubStatus?['hub'] is Map
      ? Map<String, dynamic>.from(hubStatus!['hub'] as Map)
      : null;

  List<Map<String, dynamic>> get sensors {
    final list = hubStatus?['sensors'];
    if (list is! List) return [];
    return list
        .map((e) => e is Map<String, dynamic> ? e : <String, dynamic>{})
        .toList();
  }
}
