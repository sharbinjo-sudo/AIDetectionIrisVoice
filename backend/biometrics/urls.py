from django.urls import path

from .views import (
    AuthenticationAttemptSaveView,
    BankingLoginView,
    BankingRegisterView,
    BiometricAuthenticateView,
    BiometricEnrollmentView,
    HealthView,
    IrisTrackingView,
    IrisTestView,
    LivenessChallengeVerifyView,
    LivenessChallengeView,
    SystemConfigurationView,
    UserDetailView,
    UserEnrollmentStatusView,
    UserListView,
    VoiceTestView,
)


urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path(
        "system/configuration/",
        SystemConfigurationView.as_view(),
        name="system-configuration",
    ),
    path("users/", UserListView.as_view(), name="user-list"),
    path("users/<str:user_id>/", UserDetailView.as_view(), name="user-detail"),
    path("banking/register/", BankingRegisterView.as_view(), name="banking-register"),
    path("banking/login/", BankingLoginView.as_view(), name="banking-login"),
    path(
        "users/<str:user_id>/enrollment/status/",
        UserEnrollmentStatusView.as_view(),
        name="user-enrollment-status",
    ),
    path(
        "users/<str:user_id>/enrollment/",
        BiometricEnrollmentView.as_view(),
        name="biometric-enrollment",
    ),
    path(
        "liveness/challenge/",
        LivenessChallengeView.as_view(),
        name="liveness-challenge",
    ),
    path(
        "liveness/challenge/verify/",
        LivenessChallengeVerifyView.as_view(),
        name="liveness-challenge-verify",
    ),
    path("test/iris/", IrisTestView.as_view(), name="test-iris"),
    path("test/iris/tracking/", IrisTrackingView.as_view(), name="iris-tracking"),
    path("test/voice/", VoiceTestView.as_view(), name="test-voice"),
    path(
        "biometric-authenticate/",
        BiometricAuthenticateView.as_view(),
        name="biometric-authenticate",
    ),
    path(
        "authentication-attempts/<uuid:attempt_id>/save/",
        AuthenticationAttemptSaveView.as_view(),
        name="authentication-attempt-save",
    ),
]
