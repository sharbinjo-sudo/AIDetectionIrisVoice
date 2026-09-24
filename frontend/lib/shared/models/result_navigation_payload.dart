import '../../features/irl_verification/models/verification_result.dart';

class ResultNavigationPayload {
  const ResultNavigationPayload({
    required this.result,
    required this.userId,
    required this.eyeSide,
  });

  final VerificationResult result;
  final String userId;
  final String eyeSide;
}
