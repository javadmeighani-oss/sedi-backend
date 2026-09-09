import '../../../data/dto/auth/me_profile.dart';

/// Pure rules for deciding whether a backend profile is complete enough for Gate 3.
class Gate2ProfileRules {
  Gate2ProfileRules._();

  static bool isProfileComplete(MeProfileDto me) {
    final hasName = me.name != null && me.name!.trim().isNotEmpty;
    final hasSex = me.sex != null && me.sex!.trim().isNotEmpty;
    final hasCalendar =
        me.calendarType != null && me.calendarType!.trim().isNotEmpty;
    final hasBirth =
        me.birthDay != null && me.birthMonth != null && me.birthYear != null;
    final hasPhone = me.phone != null && me.phone!.trim().isNotEmpty;
    return hasName &&
        hasSex &&
        hasCalendar &&
        hasBirth &&
        hasPhone &&
        me.userId > 0;
  }
}
