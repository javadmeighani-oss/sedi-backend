/// Merges new IDs (newest first) with existing ordered list and returns at most
/// [max] ids (newest first). Used for rolling-window storage; exposed for tests.
List<String> mergeSeenIdsRollingWindow(
  List<String> existingOrdered,
  List<String> newIds,
  int max,
) {
  final merged = [
    ...newIds,
    ...existingOrdered.where((id) => !newIds.contains(id)),
  ];
  return merged.take(max).toList();
}
