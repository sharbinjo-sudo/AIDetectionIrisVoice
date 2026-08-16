class AppException implements Exception {
  AppException({
    required this.message,
    this.code,
    this.details,
  });

  final String message;
  final String? code;
  final Object? details;

  @override
  String toString() => message;
}
