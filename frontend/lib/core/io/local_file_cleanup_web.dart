import 'package:web/web.dart' as web;

Future<void> deleteLocalFileIfExists(String? path) async {
  if (path != null && path.startsWith('blob:')) {
    web.URL.revokeObjectURL(path);
  }
}

Future<void> deleteLocalFilesIfExists(Iterable<String?> paths) async {
  for (final path in paths) {
    await deleteLocalFileIfExists(path);
  }
}
