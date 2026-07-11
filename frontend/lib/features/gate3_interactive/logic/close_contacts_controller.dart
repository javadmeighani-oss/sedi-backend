import 'package:flutter/foundation.dart';



import '../../../data/dto/gate3/caregiver_dto.dart';

import '../../../data/repositories/caregivers_repository.dart';

import '../presentation/gate3_sections_localization.dart';



class CloseContactsController extends ChangeNotifier {

  final CaregiversRepository _repo;

  final String lang;



  CloseContactsController({

    required this.lang,

    CaregiversRepository? repository,

  }) : _repo = repository ?? CaregiversRepository();



  List<CaregiverDto> contacts = [];

  bool loading = false;

  bool refreshing = false;

  String? error;

  String? actionMessage;

  final Set<int> _savingIds = {};



  Gate3SectionsLocalization get l10n => Gate3SectionsLocalization(lang);



  bool isSaving(int id) => _savingIds.contains(id);



  Future<void> load({bool isRefresh = false}) async {

    if (loading && !isRefresh) return;

    if (isRefresh) {

      refreshing = true;

    } else {

      loading = true;

    }

    error = null;

    notifyListeners();



    final res = await _repo.listCaregivers();

    if (!res.ok) {

      error = _mapError(res.error?.message);

      loading = false;

      refreshing = false;

      notifyListeners();

      return;

    }



    contacts = res.data ?? [];

    loading = false;

    refreshing = false;

    notifyListeners();

  }



  Future<bool> saveContact({

    CaregiverDto? existing,

    required String name,

    String? phone,

    String? relationship,

    bool notifyDailyStatus = false,

    bool notifyEmergency = true,

    bool notifyCareSummary = false,

    bool notifyVitalAlerts = false,

    int? emergencyPriority,

  }) async {

    actionMessage = null;

    if (existing != null) _savingIds.add(existing.id);

    notifyListeners();



    final body = existing == null

        ? CaregiverDto(

            id: 0,

            name: name,

          ).toCreateJson(

            name: name,

            phone: phone,

            relationship: relationship,

            notifyDailyStatus: notifyDailyStatus,

            notifyEmergency: notifyEmergency,

            notifyCareSummary: notifyCareSummary,

            notifyVitalAlerts: notifyVitalAlerts,

            emergencyPriority: emergencyPriority,

          )

        : existing.toUpdateJson(

            name: name,

            phone: phone,

            relationship: relationship,

            notifyDailyStatus: notifyDailyStatus,

            notifyEmergency: notifyEmergency,

            notifyCareSummary: notifyCareSummary,

            notifyVitalAlerts: notifyVitalAlerts,

            emergencyPriority: emergencyPriority,

          );



    final res = existing == null

        ? await _repo.createCaregiver(body)

        : await _repo.updateCaregiver(existing.id, body);



    if (existing != null) _savingIds.remove(existing.id);



    if (!res.ok) {

      actionMessage = l10n.saveFailed;

      notifyListeners();

      return false;

    }



    actionMessage = l10n.saveSuccess;

    await load(isRefresh: true);

    return true;

  }



  Future<bool> removeContact(CaregiverDto contact) async {

    final res = await _repo.deactivateCaregiver(contact.id);

    if (!res.ok) {

      actionMessage = l10n.saveFailed;

      notifyListeners();

      return false;

    }

    await load(isRefresh: true);

    return true;

  }



  String _mapError(String? raw) {

    if (raw == null || raw.isEmpty) return l10n.genericError();

    final lower = raw.toLowerCase();

    if (lower.contains('timeout') ||

        lower.contains('connection') ||

        lower.contains('socket')) {

      return l10n.networkError();

    }

    return l10n.genericError();

  }

}
