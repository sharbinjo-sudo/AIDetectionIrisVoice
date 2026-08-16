from django.test import TestCase
from rest_framework.test import APIClient

from .models import BiometricUser, EnrollmentStatus


class BiometricsApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = BiometricUser.objects.create(
            external_id="USR-001",
            full_name="Demo User",
            enrollment_status=EnrollmentStatus.COMPLETE,
            iris_embedding=[0.1, 0.2, 0.3],
            voice_embedding=[0.2, 0.3, 0.4],
        )

    def test_users_list_matches_frontend_shape(self):
        response = self.client.get("/api/v1/users/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("data", response.json())
        self.assertEqual(len(response.json()["data"]["results"]), 1)

    def test_enrollment_status_endpoint(self):
        response = self.client.get(
            f"/api/v1/users/{self.user.id}/enrollment/status/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["data"]["enrollment_status"],
            EnrollmentStatus.COMPLETE,
        )

    def test_save_attempt_endpoint_disabled_in_privacy_mode(self):
        response = self.client.post(
            "/api/v1/authentication-attempts/00000000-0000-0000-0000-000000000000/save/"
        )
        self.assertEqual(response.status_code, 410)

    def test_system_configuration_matches_frontend_contract(self):
        response = self.client.get("/api/v1/system/configuration/")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertTrue(data["privacy_mode"])
        self.assertEqual(data["minimum_voice_samples"], 1)
        self.assertEqual(data["minimum_iris_samples"], 1)
        self.assertIn("voice_model", data)
        self.assertIn("iris_model", data)

    def test_validation_errors_use_frontend_message_shape(self):
        response = self.client.post("/api/v1/test/voice/", data={})
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("message", payload)
        self.assertIn("errors", payload)
        self.assertIn("voice_file", payload["message"])
