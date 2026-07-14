/// Pure same-day history mapping for Gate 3 restore (no UI / audio side effects).
library;

import '../../data/dto/history_response.dart';

class RestoredChatTurn {
  final String localId;
  final String text;
  final bool isUser;
  final DateTime createdAt;

  const RestoredChatTurn({
    required this.localId,
    required this.text,
    required this.isUser,
    required this.createdAt,
  });
}

/// Select only the group whose key equals [HistoryResponse.currentGroupKey].
/// When current_group_key is absent, fall back to local-date filtering.
/// Never includes other days when the key is present.
List<RestoredChatTurn> mapSameDayHistoryTurns(
  HistoryResponse response, {
  DateTime? now,
}) {
  final HistoryGroupItem? sameDayGroup;
  final key = response.currentGroupKey;
  if (key != null && key.isNotEmpty) {
    HistoryGroupItem? matched;
    for (final group in response.items) {
      if (group.key == key) {
        matched = group;
        break;
      }
    }
    sameDayGroup = matched;
  } else {
    sameDayGroup = null;
  }

  final dated = <({DateTime at, RestoredChatTurn turn})>[];
  final Iterable<HistoryGroupItem> groups =
      sameDayGroup != null ? <HistoryGroupItem>[sameDayGroup] : response.items;

  final effectiveNow = now ?? DateTime.now();
  final todayStart =
      DateTime(effectiveNow.year, effectiveNow.month, effectiveNow.day);
  final tomorrowStart = todayStart.add(const Duration(days: 1));
  final seenTurnIds = <int>{};

  for (final group in groups) {
    for (final turn in group.turns) {
      if (seenTurnIds.contains(turn.id)) continue;
      seenTurnIds.add(turn.id);

      final created = DateTime.tryParse(turn.createdAt)?.toLocal();
      if (created == null) continue;

      if (sameDayGroup == null) {
        if (created.isBefore(todayStart) || !created.isBefore(tomorrowStart)) {
          continue;
        }
      }

      final userText = turn.userMessage.trim();
      if (userText.isNotEmpty) {
        dated.add((
          at: created,
          turn: RestoredChatTurn(
            localId: 'hist-user-${turn.id}',
            text: userText,
            isUser: true,
            createdAt: created,
          ),
        ));
      }

      final sediText = turn.sediResponse?.trim() ?? '';
      if (sediText.isNotEmpty) {
        dated.add((
          at: created.add(const Duration(milliseconds: 1)),
          turn: RestoredChatTurn(
            localId: 'hist-asst-${turn.id}',
            text: sediText,
            isUser: false,
            createdAt: created,
          ),
        ));
      }
    }
  }

  dated.sort((a, b) => a.at.compareTo(b.at));
  return dated.map((e) => e.turn).toList();
}
