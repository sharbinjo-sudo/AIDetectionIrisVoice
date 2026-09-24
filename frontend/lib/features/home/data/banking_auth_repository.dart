import 'package:dio/dio.dart';

import '../../../core/config/api_endpoints.dart';
import '../../../core/errors/error_mapper.dart';

class BankingAuthRepository {
  BankingAuthRepository(this._dio);

  final Dio _dio;

  Future<BankingAuthSession> register({
    required String fullName,
    required String mobileNumber,
    required String pin,
  }) async {
    try {
      final response = await _dio.post<dynamic>(
        ApiEndpoints.bankingRegister,
        data: {
          'full_name': fullName,
          'mobile_number': mobileNumber,
          'pin': pin,
        },
      );
      return BankingAuthSession.fromEnvelope(response.data);
    } catch (error) {
      throw ErrorMapper.map(error);
    }
  }

  Future<BankingAuthSession> login({
    required String customerId,
    required String pin,
  }) async {
    try {
      final response = await _dio.post<dynamic>(
        ApiEndpoints.bankingLogin,
        data: {'customer_id': customerId, 'pin': pin},
      );
      return BankingAuthSession.fromEnvelope(response.data);
    } catch (error) {
      throw ErrorMapper.map(error);
    }
  }
}

class BankingAuthSession {
  const BankingAuthSession({
    required this.token,
    required this.customerId,
    required this.biometricUserId,
    required this.enrollmentStatus,
    required this.enrolledEyeSide,
    required this.nextStep,
  });

  final String token;
  final String customerId;
  final String biometricUserId;
  final String enrollmentStatus;
  final String enrolledEyeSide;
  final String nextStep;

  factory BankingAuthSession.fromEnvelope(dynamic envelope) {
    final payload = envelope is Map
        ? (envelope['data'] as Map?)?.cast<String, dynamic>() ??
              envelope.cast<String, dynamic>()
        : <String, dynamic>{};
    final customer =
        (payload['customer'] as Map?)?.cast<String, dynamic>() ??
        <String, dynamic>{};

    return BankingAuthSession(
      token: payload['token']?.toString() ?? '',
      customerId: customer['customer_id']?.toString() ?? '',
      biometricUserId: customer['biometric_user_id']?.toString() ?? '',
      enrollmentStatus: customer['enrollment_status']?.toString() ?? 'PENDING',
      enrolledEyeSide:
          customer['enrolled_eye_side']?.toString().toUpperCase() == 'RIGHT'
          ? 'RIGHT'
          : 'LEFT',
      nextStep: payload['next_step']?.toString() ?? 'BIOMETRIC_ENROLLMENT',
    );
  }
}
