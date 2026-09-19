import 'package:flutter/material.dart';

import '../widgets/lifestyle_weekly_plan_view.dart';

class LifestyleExercisePage extends StatelessWidget {
  const LifestyleExercisePage({super.key});

  @override
  Widget build(BuildContext context) {
    return const LifestyleWeeklyPlanView(
      domain: LifestyleWeeklyDomain.exercise,
    );
  }
}
