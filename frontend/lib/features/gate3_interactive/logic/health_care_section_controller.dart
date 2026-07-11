import 'package:flutter/foundation.dart';



import '../../../data/dto/gate3/user_medication_dto.dart';

import '../../../data/dto/gate3/vitals_summary_dto.dart';

import '../../../data/repositories/gate3_care_repository.dart';

import '../../../data/repositories/gate3_health_repository.dart';

import '../../../data/repositories/gate3_user_data_repository.dart';

import '../presentation/gate3_sections_localization.dart';



const _medicalEventTypes = {

  'doctor_visit',

  'lab_test',

  'medical_follow_up',

  'imaging',

  'surgery',

  'care_followup',

};



class HealthCareSectionController extends ChangeNotifier {

  final Gate3HealthRepository _healthRepo;

  final Gate3CareRepository _careRepo;

  final Gate3UserDataRepository _userRepo;

  final String lang;



  HealthCareSectionController({

    required this.lang,

    Gate3HealthRepository? healthRepo,

    Gate3CareRepository? careRepo,

    Gate3UserDataRepository? userRepo,

  })  : _healthRepo = healthRepo ?? Gate3HealthRepository(),

        _careRepo = careRepo ?? Gate3CareRepository(),

        _userRepo = userRepo ?? Gate3UserDataRepository();



  bool loading = false;

  bool refreshing = false;

  String? error;

  VitalsSummaryDto? vitals;

  List<UserMedicationDto> medications = [];

  List<Map<String, dynamic>> doctors = [];

  List<Map<String, dynamic>> events = [];

  List<Map<String, dynamic>> recommendations = [];

  List<Map<String, dynamic>> followUps = [];

  List<String> carePlanNotes = [];

  DateTime? lastLoadedAt;

  String? actionMessage;



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



    final vitalsRes = await _healthRepo.fetchVitalsSummary();

    final medsRes = await _userRepo.fetchMedications();

    final doctorsRes = await _userRepo.fetchDoctors();

    final eventsRes = await _userRepo.fetchEvents();

    final recsRes = await _careRepo.fetchRecommendations();

    final followRes = await _careRepo.fetchFollowUps();

    final ctxRes = await _careRepo.fetchContext();



    if (!vitalsRes.ok && vitals == null) {

      error = l10n.genericError();

    } else if (vitalsRes.ok && vitalsRes.data != null) {

      vitals = VitalsSummaryDto.fromJson(vitalsRes.data);

    }



    if (medsRes.ok) {

      medications = (medsRes.data ?? [])

          .map((e) => UserMedicationDto.fromJson(e))

          .toList();

    }

    if (doctorsRes.ok) doctors = doctorsRes.data ?? doctors;

    if (eventsRes.ok) events = eventsRes.data ?? events;

    if (recsRes.ok) recommendations = recsRes.data ?? recommendations;

    if (followRes.ok) followUps = followRes.data ?? followUps;



    final ctx = ctxRes.data;

    if (ctx is Map<String, dynamic>) {

      final interp = ctx['care_plan_interpretation'];

      if (interp is List) {

        carePlanNotes = interp.map((e) => e.toString()).toList();

      }

    }



    lastLoadedAt = DateTime.now();

    loading = false;

    refreshing = false;

    notifyListeners();

  }



  Future<bool> updateMedicationSchedule(UserMedicationDto med, {

    bool? reminderEnabled,

    List<String>? reminderTimes,

    int? intervalHours,

    String? timezone,

    double? remainingQuantity,

    String? quantityUnit,

    double? refillThreshold,

  }) async {

    actionMessage = null;

    final body = med.toScheduleUpdateJson(

      reminderEnabled: reminderEnabled,

      reminderTimes: reminderTimes,

      intervalHours: intervalHours,

      timezone: timezone,

      remainingQuantity: remainingQuantity,

      quantityUnit: quantityUnit,

      refillThreshold: refillThreshold,

    );

    final res = await _userRepo.updateMedication(med.id, body);

    if (!res.ok) {

      actionMessage = l10n.saveFailed;

      notifyListeners();

      return false;

    }

    actionMessage = l10n.saveSuccess;

    await load(isRefresh: true);

    return true;

  }



  List<Map<String, dynamic>> get medicalEvents {

    return events.where((e) {

      final type = e['event_type']?.toString() ?? '';

      if (_medicalEventTypes.contains(type)) return true;

      final domain = e['event_domain']?.toString() ?? '';

      return domain == 'medical' ||

          domain == 'care' ||

          (e['doctor_id'] != null);

    }).toList();

  }

}
