import 'package:flutter/material.dart';

import '../../../../core/locale/sedi_locale_controller.dart';
import '../../../../core/theme/app_theme.dart';
import '../lifestyle_l10n.dart';
import 'lifestyle_page.dart';

class LifestyleExercisePage extends StatelessWidget {
  const LifestyleExercisePage({super.key});

  static const _days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  @override
  Widget build(BuildContext context) {
    final l10n = LifestyleL10n(SediLocaleController.instance.languageCode);
    return Directionality(
      textDirection: l10n.isRtl ? TextDirection.rtl : TextDirection.ltr,
      child: Scaffold(
        backgroundColor: AppTheme.gate3PaleOliveBackground,
        appBar: AppBar(
          title: Text(l10n.exercisePlan),
          backgroundColor: AppTheme.gate3PaleOliveBackground,
          foregroundColor: AppTheme.textPrimary,
          elevation: 0,
        ),
        body: ListView(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
          children: [
            Text(l10n.noExercise,
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
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Row(
                    children: [
                      SizedBox(
                        width: 48,
                        child: Text(d,
                            style: const TextStyle(
                                fontWeight: FontWeight.w700,
                                color: AppTheme.textPrimary)),
                      ),
                      const Expanded(
                        child: Text('— · — · —',
                            style: TextStyle(color: AppTheme.textSecondary)),
                      ),
                    ],
                  ),
                )),
          ],
        ),
      ),
    );
  }
}
