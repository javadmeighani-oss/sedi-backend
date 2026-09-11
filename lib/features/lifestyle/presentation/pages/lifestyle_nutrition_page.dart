import 'package:flutter/material.dart';

import '../../../../core/locale/sedi_locale_controller.dart';
import '../../../../core/theme/app_theme.dart';
import '../lifestyle_l10n.dart';
import 'lifestyle_page.dart';

class LifestyleNutritionPage extends StatelessWidget {
  const LifestyleNutritionPage({super.key});

  static const _days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  @override
  Widget build(BuildContext context) {
    final l10n = LifestyleL10n(SediLocaleController.instance.languageCode);
    final meals = [l10n.breakfast, l10n.lunch, l10n.dinner, l10n.snack];
    return Directionality(
      textDirection: l10n.isRtl ? TextDirection.rtl : TextDirection.ltr,
      child: Scaffold(
        backgroundColor: AppTheme.gate3PaleOliveBackground,
        appBar: AppBar(
          title: Text(l10n.nutritionPlan),
          backgroundColor: AppTheme.gate3PaleOliveBackground,
          foregroundColor: AppTheme.textPrimary,
          elevation: 0,
        ),
        body: ListView(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
          children: [
            Text(l10n.noNutrition,
                style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: AppTheme.textPrimary)),
            const SizedBox(height: 8),
            Text(l10n.talkToCreate,
                style: const TextStyle(color: AppTheme.textSecondary)),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: () => openLifestyleChat(context),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.gate2ButtonOlive,
                foregroundColor: AppTheme.backgroundWhite,
              ),
              child: Text(l10n.openChat),
            ),
            const SizedBox(height: 28),
            ..._days.map((d) => Padding(
                  padding: const EdgeInsets.only(bottom: 14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(d,
                          style: const TextStyle(
                              fontWeight: FontWeight.w700,
                              color: AppTheme.textPrimary)),
                      ...meals.map((m) => Padding(
                            padding: const EdgeInsets.only(top: 4),
                            child: Text('• $m — —',
                                style: const TextStyle(
                                    color: AppTheme.textSecondary)),
                          )),
                    ],
                  ),
                )),
          ],
        ),
      ),
    );
  }
}
