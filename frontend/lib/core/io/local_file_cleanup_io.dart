import 'dart:io';

Future<void> deleteLocalFileIfExists(String? path) async {
  if (path == null || path.isEmpty) {
    return;
  }
  final file = File(path);
  if (await file.exists()) {
    await file.delete();
  }
}

Future<void> deleteLocalFilesIfExists(Iterable<String?> paths) async {
  for (final path in paths) {
    await deleteLocalFileIfExists(path);
  }
}
