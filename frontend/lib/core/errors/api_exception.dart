import 'package:dio/dio.dart';

class ApiException implements Exception {
  ApiException({required this.message, this.code, this.statusCode});

  final String message;
  final String? code;
  final int? statusCode;

  factory ApiException.fromDio(DioException error) {
    final data = error.response?.data;
    final message = data is Map<String, dynamic>
        ? data['message']?.toString() ??
              data['detail']?.toString() ??
              error.message ??
              'Request failed.'
        : error.message ?? 'Request failed.';
    final code = data is Map<String, dynamic> ? data['code']?.toString() : null;

    return ApiException(
      message: message,
      code: code,
      statusCode: error.response?.statusCode,
    );
  }

  @override
  String toString() => message;
}
