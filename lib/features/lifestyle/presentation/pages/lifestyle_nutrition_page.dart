import 'package:flutter/material.dart';

import '../widgets/lifestyle_weekly_plan_view.dart';

class LifestyleNutritionPage extends StatelessWidget {
  const LifestyleNutritionPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const LifestyleWeeklyPlanView(
      domain: LifestyleWeeklyDomain.nutrition,
    );
  }
}
