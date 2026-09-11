import 'package:flutter/material.dart';

import '../../../../core/locale/calendar_date_math.dart';
import '../../../../core/locale/sedi_locale_controller.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../data/dto/lifestyle/lifestyle_weekly_plan_dto.dart';
import '../../../../services/lifestyle/lifestyle_weekly_plan_service.dart';
import '../lifestyle_l10n.dart';
import '../pages/lifestyle_page.dart';

enum LifestyleWeeklyDomain { nutrition, exercise }

/// Shared weekly-plan presentation for Nutrition and Exercise.
/// Renders backend days in order; never fabricates plan content.
class LifestyleWeeklyPlanView extends StatefulWidget {
  final LifestyleWeeklyDomain domain;
  final LifestyleWeeklyPlanService? service;

  const LifestyleWeeklyPlanView({
    super.key,
    required this.domain,
    this.service,
  });

  @override
  State<LifestyleWeeklyPlanView> createState() =>
      _LifestyleWeeklyPlanViewState();
}

class _LifestyleWeeklyPlanViewState extends State<LifestyleWeeklyPlanView> {
  late final LifestyleWeeklyPlanService _svc =
      widget.service ?? LifestyleWeeklyPlanService();
  LifestyleWeeklyPlanDto? _plan;
  bool _loading = true;
  bool _fetchFailed = false;

  LifestyleL10n get _l10n =>
      LifestyleL10n(SediLocaleController.instance.languageCode);

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _fetchFailed = false;
    });
    final res = await _svc.fetchWeeklyPlan();
    if (!mounted) return;
    setState(() {
      _loading = false;
      if (res.ok && res.data != null) {
        _plan = res.data;
        _fetchFailed = false;
      } else {
        _plan = null;
        _fetchFailed = true;
      }
    });
  }

  String get _effectiveState {
    if (_fetchFailed || _plan == null) return 'unavailable';
    final s = _plan!.state;
    if (s == 'active' ||
        s == 'empty' ||
        s == 'review_due' ||
        s == 'unavailable') {
      return s;
    }
    return 'unavailable';
  }

  List<LifestyleWeeklyActionDto> _actionsFor(LifestyleWeeklyDayDto day) {
    switch (widget.domain) {
      case LifestyleWeeklyDomain.nutrition:
        return day.nutrition;
      case LifestyleWeeklyDomain.exercise:
        return day.exercise;
    }
  }

  String _actionLine(LifestyleWeeklyActionDto a, LifestyleL10n l10n) {
    final parts = <String>[];
    final title = a.title ?? a.activityTitle;
    if (title != null && title.isNotEmpty) parts.add(title);
    if (a.localTime != null && a.localTime!.isNotEmpty) {
      parts.add(a.localTime!);
    }
    if (widget.domain == LifestyleWeeklyDomain.nutrition &&
        a.mealSlot != null &&
        a.mealSlot!.isNotEmpty) {
      parts.add(l10n.mealSlotLabel(a.mealSlot!));
    }
    if (widget.domain == LifestyleWeeklyDomain.exercise) {
      if (a.activityType != null && a.activityType!.isNotEmpty) {
        parts.add(a.activityType!);
      }
      if (a.durationMinutes != null) {
        parts.add(l10n.durationMinutes(a.durationMinutes!));
      }
    }
    if (a.status != null && a.status!.isNotEmpty) {
      parts.add(l10n.scheduleStatusLabel(a.status!));
    }
    return parts.isEmpty ? '•' : '• ${parts.join(' · ')}';
  }

  @override
  Widget build(BuildContext context) {
    final l10n = _l10n;
    final isNutrition = widget.domain == LifestyleWeeklyDomain.nutrition;
    final title = isNutrition ? l10n.nutritionPlan : l10n.exercisePlan;
    final draft =
        isNutrition ? l10n.reviewNutritionDraft : l10n.reviewExerciseDraft;

    return Directionality(
      textDirection: l10n.isRtl ? TextDirection.rtl : TextDirection.ltr,
      child: Scaffold(
        backgroundColor: AppTheme.gate3PaleOliveBackground,
        appBar: AppBar(
          title: Text(title),
          backgroundColor: AppTheme.gate3PaleOliveBackground,
          foregroundColor: AppTheme.textPrimary,
          elevation: 0,
        ),
        body: RefreshIndicator(
          onRefresh: _load,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
            children: [
              if (_loading)
                const Padding(
                  padding: EdgeInsets.only(top: 40),
                  child: Center(
                    child: CircularProgressIndicator(
                      color: AppTheme.gate2ButtonOlive,
                    ),
                  ),
                )
              else ...[
                _buildStateHeader(l10n),
                const SizedBox(height: 16),
                ElevatedButton(
                  onPressed: () =>
                      openLifestyleChat(context, initialDraft: draft),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.gate2ButtonOlive,
                    foregroundColor: AppTheme.backgroundWhite,
                  ),
                  child: Text(l10n.openChat),
                ),
                if (_effectiveState == 'active' ||
                    _effectiveState == 'review_due') ...[
                  const SizedBox(height: 28),
                  ..._buildDays(l10n),
                ],
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildStateHeader(LifestyleL10n l10n) {
    final isNutrition = widget.domain == LifestyleWeeklyDomain.nutrition;
    switch (_effectiveState) {
      case 'empty':
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              isNutrition ? l10n.noNutrition : l10n.noExercise,
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w600,
                color: AppTheme.textPrimary,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              l10n.talkToCreate,
              style: const TextStyle(color: AppTheme.textSecondary),
            ),
          ],
        );
      case 'review_due':
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              l10n.reviewDueTitle,
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w600,
                color: AppTheme.textPrimary,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              l10n.reviewDueBody,
              style: const TextStyle(color: AppTheme.textSecondary),
            ),
          ],
        );
      case 'unavailable':
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              l10n.planUnavailable,
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w600,
                color: AppTheme.textPrimary,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              l10n.planUnavailableBody,
              style: const TextStyle(color: AppTheme.textSecondary),
            ),
          ],
        );
      default: // active
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              isNutrition ? l10n.nutritionActive : l10n.exerciseActive,
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w600,
                color: AppTheme.textPrimary,
              ),
            ),
            if (_plan?.cycleStart != null && _plan!.cycleStart!.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                l10n.cycleRangeLabel(
                  CalendarDateMath.formatIsoForLanguage(
                    _plan!.cycleStart!,
                    l10n.lang,
                  ),
                  _plan!.cycleEnd != null && _plan!.cycleEnd!.isNotEmpty
                      ? CalendarDateMath.formatIsoForLanguage(
                          _plan!.cycleEnd!,
                          l10n.lang,
                        )
                      : '',
                ),
                style: const TextStyle(color: AppTheme.textSecondary),
              ),
            ],
          ],
        );
    }
  }

  List<Widget> _buildDays(LifestyleL10n l10n) {
    final days = _plan?.days ?? const <LifestyleWeeklyDayDto>[];
    // Backend provides exact 7-day order — do not reorder or invent days.
    return days.map((day) {
      final weekday = CalendarDateMath.weekdayFromIso(day.localDate);
      final weekdayLabel =
          weekday == null ? '' : l10n.weekdayShort(weekday);
      final dateLabel = day.localDate.isEmpty
          ? ''
          : CalendarDateMath.formatIsoForLanguage(day.localDate, l10n.lang);
      final header = [
        if (weekdayLabel.isNotEmpty) weekdayLabel,
        if (dateLabel.isNotEmpty) dateLabel,
      ].join(' · ');
      final actions = _actionsFor(day);
      return Padding(
        padding: const EdgeInsets.only(bottom: 14),
        child: Material(
          color: AppTheme.gate2CardWhite,
          borderRadius: BorderRadius.circular(AppTheme.radiusLarge),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (header.isNotEmpty)
                  Text(
                    header,
                    style: const TextStyle(
                      fontWeight: FontWeight.w700,
                      color: AppTheme.textPrimary,
                    ),
                  ),
                if (actions.isEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text(
                      l10n.noActionsThisDay,
                      style: const TextStyle(color: AppTheme.textSecondary),
                    ),
                  )
                else
                  ...actions.map(
                    (a) => Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text(
                        _actionLine(a, l10n),
                        style: const TextStyle(color: AppTheme.textSecondary),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      );
    }).toList();
  }
}
