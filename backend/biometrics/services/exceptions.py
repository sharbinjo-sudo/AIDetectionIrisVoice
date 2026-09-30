class BiometricServiceError(Exception):
    status_code = 400


class BiometricValidationError(BiometricServiceError):
    status_code = 400


class BiometricProcessingError(BiometricServiceError):
    status_code = 422


class SpoofDetectedError(BiometricServiceError):
    """A dedicated anti-spoofing model reported a presentation attack."""

    status_code = 403


class ModelUnavailableError(BiometricServiceError):
    status_code = 503


class EnrollmentIncompleteError(BiometricServiceError):
    status_code = 409
