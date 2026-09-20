import 'package:flutter/material.dart';

import '../../../../core/locale/sedi_locale_controller.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../gate3_interactive/presentation/gate3_composer_draft_bus.dart';
import '../../../gate3_interactive/presentation/widgets/a3_page_app_bar.dart';
import '../lifestyle_l10n.dart';
import 'lifestyle_exercise_page.dart';
import 'lifestyle_health_page.dart';
import 'lifestyle_history_page.dart';
import 'lifestyle_nutrition_page.dart';
import 'lifestyle_schedule_page.dart';

/// A3 Lifestyle hub — exactly five primary sections. Old sleep/water/mood UI retired here.
class LifestylePage extends StatelessWidget {
  const LifestylePage({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = LifestyleL10n(SediLocaleController.instance.languageCode);
    final cards = <_HubCard>[
      _HubCard(l10n.health, Icons.favorite_border, const LifestyleHealthPage()),
      _HubCard(l10n.myHistory, Icons.history, const LifestyleHistoryPage()),
      _HubCard(
          l10n.mySchedule, Icons.event_note_outlined, const LifestyleSchedulePage()),
      _HubCard(l10n.nutritionPlan, Icons.restaurant_outlined,
          const LifestyleNutritionPage()),
      _HubCard(l10n.exercisePlan, Icons.directions_run_outlined,
          const LifestyleExercisePage()),
    ];

    return Directionality(
      textDirection: l10n.isRtl ? TextDirection.rtl : TextDirection.ltr,
      child: Scaffold(
        backgroundColor: AppTheme.gate3PaleOliveBackground,
        appBar: A3PageAppBar(
          title: Text(l10n.title),
        ),
        body: ListView.separated(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
          itemCount: cards.length,
          separatorBuilder: (_, __) => const SizedBox(height: 12),
          itemBuilder: (context, i) {
            final c = cards[i];
            return Material(
              color: AppTheme.gate2CardWhite,
              borderRadius: BorderRadius.circular(AppTheme.radiusLarge),
              child: InkWell(
                borderRadius: BorderRadius.circular(AppTheme.radiusLarge),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(builder: (_) => c.page),
                ),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
                  child: Row(
                    children: [
                      Icon(c.icon, color: AppTheme.gate2ButtonOlive),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Text(
                          c.title,
                          style: const TextStyle(
                            fontSize: 17,
                            fontWeight: FontWeight.w600,
                            color: AppTheme.textPrimary,
                          ),
                        ),
                      ),
                      const Icon(Icons.chevron_right, color: AppTheme.textSecondary),
                    ],
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}

class _HubCard {
  final String title;
  final IconData icon;
  final Widget page;
  const _HubCard(this.title, this.icon, this.page);
}

/// Opens canonical existing A3 chat (presentation CTA only).
/// Pops nested Lifestyle routes back to root A3 and seeds the composer draft.
/// Never pushes a second [Gate3InteractivePage]; never auto-sends.
void openLifestyleChat(BuildContext context, {String? initialDraft}) {
  final draft = initialDraft?.trim();
  if (draft != null && draft.isNotEmpty) {
    Gate3ComposerDraftBus.instance.publish(draft);
  }
  Navigator.of(context).popUntil((route) => route.isFirst);
}
