import 'package:dio/dio.dart';

import 'app_exception.dart';

class ErrorMapper {
  const ErrorMapper._();

  static AppException map(Object error) {
    if (error is AppException) {
      return error;
    }
    if (error is DioException) {
      final data = error.response?.data;
      final message = data is Map<String, dynamic>
          ? data['message']?.toString() ??
                data['detail']?.toString() ??
                _flattenFieldErrors(data['errors']) ??
                _flattenFieldErrors(data) ??
                _networkFallback(error)
          : _networkFallback(error);
      final code = data is Map<String, dynamic>
          ? data['code']?.toString() ?? error.response?.statusCode?.toString()
          : error.response?.statusCode?.toString();
      return AppException(message: message, code: code, details: error);
    }
    return AppException(message: error.toString(), details: error);
  }

  static String? _flattenFieldErrors(Object? value) {
    if (value == null) {
      return null;
    }
    if (value is Map) {
      final messages = <String>[];
      for (final entry in value.entries) {
        final nested = _flattenFieldErrors(entry.value);
        if (nested != null && nested.isNotEmpty) {
          messages.add('${entry.key}: $nested');
        }
      }
      return messages.isEmpty ? null : messages.join('; ');
    }
    if (value is List) {
      final messages = value
          .map(_flattenFieldErrors)
          .whereType<String>()
          .where((message) => message.isNotEmpty)
          .toList();
      return messages.isEmpty ? null : messages.join(', ');
    }
    final message = value.toString();
    return message.isEmpty ? null : message;
  }

  static String _networkFallback(DioException error) {
    if (error.type == DioExceptionType.connectionError ||
        error.type == DioExceptionType.connectionTimeout) {
      return 'Cannot reach the verification server. Check that Django is '
          'running and that the API address is correct.';
    }
    return error.message ?? 'The request could not be completed.';
  }
}
