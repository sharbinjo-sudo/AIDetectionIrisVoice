import '../../features/irl_verification/models/verification_result.dart';

class ResultNavigationPayload {
  const ResultNavigationPayload({
    required this.result,
  });

  final VerificationResult result;
}
