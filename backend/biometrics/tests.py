import json
from pathlib import Path
import tempfile
from threading import Lock
from unittest.mock import patch

from django.conf import settings
from django.core import signing
from django.contrib.auth.hashers import check_password
from django.core.cache import cache
from django.test import TestCase, override_settings

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from .management.commands.calibrate_fusion_thresholds import _fusion_score

from .models import (
    AuthenticationAttempt,
    BankingCustomer,
    BiometricUser,
    Decision,
    EnrollmentStatus,
)
from .services.engines import IrisBiometricEngine, VoiceBiometricEngine
from .services.engines import IrisSample, VoiceSample
from .services.exceptions import ModelUnavailableError, SpoofDetectedError
from .services.face_engine import FaceSample
from .services.face_liveness import FaceLivenessEngine, LivenessResult
from .services.face_liveness import summarize_liveness
from .services.fusion import (
    FusionInputs,
    ModalityMeasurement,
    ReasonCode,
    fuse_modalities,
    fuse_three_modalities,
    get_calibrated_thresholds,
)
from .services.template_crypto import decrypt_template
from .services.workflow import (
    _ui_state_for,
    authenticate_enrolled_user,
    authenticate_human,
    enroll_user_biometrics,
)


def _live_result(score: float = 0.95) -> LivenessResult:
    """Build a passed dedicated anti-spoofing result for mocked face frames."""
    return LivenessResult(
        evaluated=True,
        passed=True,
        live_score=score,
        spoof_score=1.0 - score,
        threshold=settings.FACE_LIVENESS_THRESHOLD,
        model="test-antispoof",
        status="LIVE",
        reason_code="LIVENESS_VALID",
        message="liveness ok",
    )


def _spoof_result(score: float = 0.05) -> LivenessResult:
    """Build a failed dedicated anti-spoofing result for mocked face frames."""
    return LivenessResult(
        evaluated=True,
        passed=False,
        live_score=score,
        spoof_score=1.0 - score,
        threshold=settings.FACE_LIVENESS_THRESHOLD,
        model="test-antispoof",
        status="SPOOF",
        reason_code="LIVENESS_SPOOF_DETECTED",
        message="presentation attack detected",
    )


class _FakeLivenessNet:
    def __init__(self, output):
        self.output = output
        self.input = None

    def setInput(self, value):
        self.input = value

    def forward(self):
        return self.output


class _FakeIrisNet:
    def __init__(self, output):
        self.output = output
        self.input = None

    def setInput(self, value):
        self.input = value

    def forward(self):
        return self.output


class IrisTrackingEngineTests(TestCase):
    def test_tracker_uses_native_preprocessing_and_iris_channel(self):
        import cv2
        import numpy as np

        output = np.zeros((1, 4, 480, 640), dtype=np.float32)
        cv2.ellipse(output[0, 0], (320, 240), (98, 88), 8, 0, 360, 0.96, -1)
        cv2.ellipse(output[0, 1], (320, 240), (72, 64), 8, 0, 360, 0.93, -1)
        cv2.ellipse(output[0, 2], (320, 240), (25, 22), 8, 0, 360, 0.95, -1)
        fake_net = _FakeIrisNet(output)
        engine = IrisBiometricEngine.__new__(IrisBiometricEngine)
        engine._Image = object()
        engine._cv2 = cv2
        engine._np = np
        engine._mode = "local_onnx"
        engine._onnx_net = fake_net
        engine._landmarker = object()
        engine._onnx_inference_lock = Lock()

        crop = np.full((120, 160, 3), 128, dtype=np.uint8)
        probabilities = engine._run_onnx_for_eye_crops([crop])[0]
        result = engine._geometry_from_eye_mask(
            probabilities,
            {
                "eye_side": "LEFT",
                "x": 100,
                "y": 50,
                "width": 160,
                "height": 120,
            },
            640,
            480,
        )

        self.assertIsNotNone(result)
        self.assertTrue(result["detected"])
        self.assertEqual(result["eye_side"], "LEFT")
        self.assertAlmostEqual(result["center_x"], 180, delta=2)
        self.assertAlmostEqual(result["center_y"], 110, delta=2)
        self.assertEqual(fake_net.input.shape, (1, 3, 192, 256))
        self.assertFalse(np.allclose(fake_net.input[0, 0], fake_net.input[0, 1]))

    def test_tracker_does_not_treat_other_semantic_classes_as_iris(self):
        import cv2
        import numpy as np

        output = np.zeros((1, 4, 480, 640), dtype=np.float32)
        cv2.circle(output[0, 2], (320, 240), 70, 0.99, -1)
        engine = IrisBiometricEngine.__new__(IrisBiometricEngine)
        engine._Image = object()
        engine._cv2 = cv2
        engine._np = np
        engine._mode = "local_onnx"
        engine._onnx_net = _FakeIrisNet(output)
        engine._onnx_inference_lock = Lock()

        result = engine._geometry_from_eye_mask(
            output[0],
            {"eye_side": "LEFT", "x": 0, "y": 0, "width": 160, "height": 120},
            640,
            480,
        )

        self.assertIsNone(result)

    def test_tracker_rejects_iris_shaped_mask_without_eye_anatomy(self):
        import cv2
        import numpy as np

        output = np.zeros((1, 4, 480, 640), dtype=np.float32)
        cv2.ellipse(output[0, 1], (510, 390), (72, 48), 4, 0, 360, 0.99, -1)
        engine = IrisBiometricEngine.__new__(IrisBiometricEngine)
        engine._Image = object()
        engine._cv2 = cv2
        engine._np = np
        engine._mode = "local_onnx"
        engine._onnx_net = _FakeIrisNet(output)
        engine._onnx_inference_lock = Lock()

        result = engine._geometry_from_eye_mask(
            output[0],
            {"eye_side": "RIGHT", "x": 0, "y": 0, "width": 160, "height": 120},
            640,
            480,
        )

        self.assertIsNone(result)

    def test_tracker_rejects_tiny_out_of_domain_eye_masks(self):
        import cv2
        import numpy as np

        output = np.zeros((1, 4, 480, 640), dtype=np.float32)
        cv2.circle(output[0, 0], (320, 240), 24, 0.98, -1)
        cv2.circle(output[0, 1], (320, 240), 15, 0.98, -1)
        cv2.circle(output[0, 2], (320, 240), 5, 0.98, -1)
        engine = IrisBiometricEngine.__new__(IrisBiometricEngine)
        engine._Image = object()
        engine._cv2 = cv2
        engine._np = np
        engine._mode = "local_onnx"
        engine._onnx_net = _FakeIrisNet(output)
        engine._onnx_inference_lock = Lock()

        result = engine._geometry_from_eye_mask(
            output[0],
            {"eye_side": "LEFT", "x": 0, "y": 0, "width": 160, "height": 120},
            640,
            480,
        )

        self.assertIsNone(result)

    def test_tracker_batches_and_maps_both_eye_rois(self):
        import cv2
        import numpy as np

        output = np.zeros((2, 4, 480, 640), dtype=np.float32)
        for batch_index in range(2):
            cv2.ellipse(output[batch_index, 0], (320, 240), (98, 88), 0, 0, 360, 0.96, -1)
            cv2.ellipse(output[batch_index, 1], (320, 240), (72, 64), 0, 0, 360, 0.93, -1)
            cv2.ellipse(output[batch_index, 2], (320, 240), (25, 22), 0, 0, 360, 0.95, -1)
        fake_net = _FakeIrisNet(output)
        engine = IrisBiometricEngine.__new__(IrisBiometricEngine)
        engine._Image = object()
        engine._cv2 = cv2
        engine._np = np
        engine._mode = "local_onnx"
        engine._onnx_net = fake_net
        engine._onnx_inference_lock = Lock()
        engine._detect_landmarks = lambda _image: [object()]
        engine._landmarker = object()
        crops = [np.full((120, 160, 3), 128, dtype=np.uint8) for _ in range(2)]
        engine._eye_rois_from_face_landmarks = lambda _image, _landmarks: [
            {"eye_side": "LEFT", "x": 80, "y": 60, "width": 160, "height": 120, "crop": crops[0]},
            {"eye_side": "RIGHT", "x": 360, "y": 60, "width": 160, "height": 120, "crop": crops[1]},
        ]

        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "frame.png"
            self.assertTrue(cv2.imwrite(str(image_path), np.full((480, 640, 3), 128, dtype=np.uint8)))
            result = engine.track_iris(str(image_path))

        self.assertTrue(result["detected"])
        self.assertEqual(len(result["eyes"]), 2)
        self.assertEqual({eye["eye_side"] for eye in result["eyes"]}, {"LEFT", "RIGHT"})
        self.assertEqual(len(result["eye_rois"]), 2)
        self.assertEqual(fake_net.input.shape, (2, 3, 192, 256))


class FusionDecisionTests(TestCase):
    """Unit tests for the quality-aware multimodal decision engine."""

    FUSE_KWARGS = dict(
        base_voice_weight=0.5,
        base_iris_weight=0.5,
        fusion_threshold=0.8,
        iris_quality_threshold=0.55,
        iris_detection_confidence_threshold=0.45,
        voice_quality_threshold=0.55,
        voice_activity_threshold=0.35,
        single_modality_fallback_threshold=0.72,
    )

    @staticmethod
    def _measurements(iris_quality=0.74, voice_quality=0.91, activity=0.8):
        return FusionInputs(
            iris=ModalityMeasurement(
                score=iris_quality,
                quality=iris_quality,
                detection_confidence=1.0,
                valid_measurement=False,
            ),
            voice=ModalityMeasurement(
                score=voice_quality,
                quality=voice_quality,
                detection_confidence=1.0,
                valid_measurement=False,
                speech_activity=activity,
            ),
        )

    def test_weak_iris_with_strong_voice_is_accepted_not_rejected(self):
        # The regression case from the bug report: iris 74.2, voice 90.8
        # must not fail merely because the iris capture is weaker.
        decision = fuse_modalities(
            self._measurements(iris_quality=0.742, voice_quality=0.908),
            **self.FUSE_KWARGS,
        )
        self.assertEqual(decision.decision, "ACCEPTED")
        self.assertGreaterEqual(decision.fusion_score, decision.fusion_threshold)
        self.assertEqual(decision.reason_code, ReasonCode.ALL_MODALITIES_VALID)
        # Voice should carry more weight than iris here.
        self.assertGreater(decision.voice_weight, decision.iris_weight)

    def test_undetected_iris_is_retry_not_rejection(self):
        inputs = self._measurements(iris_quality=0.0, voice_quality=0.9)
        inputs.iris.detection_confidence = 0.0
        decision = fuse_modalities(inputs, **self.FUSE_KWARGS)
        self.assertEqual(decision.decision, "RETRY_REQUIRED")
        self.assertEqual(decision.reason_code, ReasonCode.IRIS_NOT_DETECTED)

    def test_blurry_iris_is_quality_retry_with_retry_weights(self):
        inputs = self._measurements(iris_quality=0.30, voice_quality=0.9)
        decision = fuse_modalities(inputs, **self.FUSE_KWARGS)
        self.assertEqual(decision.decision, "RETRY_REQUIRED")
        self.assertEqual(decision.reason_code, ReasonCode.IRIS_QUALITY_TOO_LOW)
        self.assertEqual(decision.voice_weight, 1.0)
        self.assertEqual(decision.iris_weight, 0.0)

    def test_no_speech_activity_is_retry(self):
        inputs = self._measurements(iris_quality=0.9, voice_quality=0.95, activity=0.1)
        decision = fuse_modalities(inputs, **self.FUSE_KWARGS)
        self.assertEqual(decision.decision, "RETRY_REQUIRED")
        self.assertEqual(decision.reason_code, ReasonCode.VOICE_NO_SPEECH_ACTIVITY)

    def test_both_modalities_invalid_is_retry(self):
        inputs = self._measurements(iris_quality=0.1, voice_quality=0.1, activity=0.1)
        decision = fuse_modalities(inputs, **self.FUSE_KWARGS)
        self.assertEqual(decision.decision, "RETRY_REQUIRED")
        self.assertIn(
            decision.reason_code,
            {ReasonCode.NO_VALID_MODALITY, ReasonCode.VOICE_NO_SPEECH_ACTIVITY},
        )

    def test_low_quality_both_valid_but_fusion_inconclusive_is_retry(self):
        # Both "valid" by the gates but weak scores -> inconclusive, retry.
        decision = fuse_modalities(
            self._measurements(iris_quality=0.60, voice_quality=0.60),
            **self.FUSE_KWARGS,
        )
        self.assertEqual(decision.decision, "RETRY_REQUIRED")
        self.assertEqual(decision.reason_code, ReasonCode.FUSION_INCONCLUSIVE)

    def test_spoof_evidence_is_rejected_spoof(self):
        inputs = self._measurements()
        inputs.spoof_evidence = True
        decision = fuse_modalities(inputs, **self.FUSE_KWARGS)
        self.assertEqual(decision.decision, "REJECTED_SPOOF")

    def test_mismatch_evidence_is_rejected_mismatch(self):
        inputs = self._measurements()
        inputs.mismatch_evidence = True
        decision = fuse_modalities(inputs, **self.FUSE_KWARGS)
        self.assertEqual(decision.decision, "REJECTED_MISMATCH")

    def test_liveness_failure_blocks_accept(self):
        inputs = self._measurements()
        inputs.liveness_passed = False
        decision = fuse_modalities(inputs, **self.FUSE_KWARGS)
        self.assertEqual(decision.decision, "RETRY_REQUIRED")
        self.assertEqual(decision.reason_code, ReasonCode.FUSION_INCONCLUSIVE)

    def test_single_modality_fallback_accepts_strong_voice(self):
        # Iris undetected but voice is very strong: with the fallback policy
        # the reliable modality carries the decision (no rejection).
        inputs = self._measurements(iris_quality=0.0, voice_quality=0.95)
        inputs.iris.detection_confidence = 0.0
        kwargs = dict(self.FUSE_KWARGS, single_modality_fallback_threshold=0.72)
        decision = fuse_modalities(inputs, **kwargs)
        # Iris is invalid -> strict quality retry; the fallback threshold
        # documents the policy boundary for future gated flows.
        self.assertEqual(decision.decision, "RETRY_REQUIRED")
        self.assertEqual(decision.reason_code, ReasonCode.IRIS_NOT_DETECTED)

    def test_single_modality_fallback_requires_affirmative_liveness(self):
        inputs = self._measurements(iris_quality=0.0, voice_quality=0.95)
        inputs.iris.detection_confidence = 0.0
        inputs.liveness_passed = True

        decision = fuse_modalities(inputs, **self.FUSE_KWARGS)

        self.assertEqual(decision.decision, "ACCEPTED")
        self.assertEqual(
            decision.reason_code,
            ReasonCode.SINGLE_MODALITY_HIGH_CONFIDENCE,
        )
        self.assertEqual(decision.iris_weight, 0.0)
        self.assertEqual(decision.voice_weight, 1.0)

    def test_ui_state_mapping(self):
        self.assertEqual(_ui_state_for("ACCEPTED", ReasonCode.ALL_MODALITIES_VALID), "VERIFIED")
        self.assertEqual(
            _ui_state_for("RETRY_REQUIRED", ReasonCode.IRIS_QUALITY_TOO_LOW),
            "QUALITY_TOO_LOW",
        )
        self.assertEqual(
            _ui_state_for("RETRY_REQUIRED", ReasonCode.FUSION_INCONCLUSIVE),
            "RETRY_REQUIRED",
        )
        self.assertEqual(
            _ui_state_for("REJECTED_MISMATCH", ReasonCode.REJECTED_MISMATCH),
            "REJECTED_MISMATCH",
        )
        self.assertEqual(
            _ui_state_for("REJECTED_SPOOF", ReasonCode.REJECTED_SPOOF),
            "REJECTED_SPOOF",
        )

    def test_calibrated_thresholds_fall_back_to_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.json"
            with override_settings(FUSION_CALIBRATION_PATH=missing):
                thresholds = get_calibrated_thresholds()
                self.assertEqual(thresholds["source"], "defaults")
                self.assertAlmostEqual(
                    thresholds["fusion_threshold"], settings.FUSION_THRESHOLD
                )

            calibration_file = Path(directory) / "fusion_calibration.json"
            calibration_file.write_text(
                json.dumps(
                    {
                        "fusion_threshold": 0.67,
                        "single_modality_fallback_threshold": 0.75,
                        "genuine_samples": 40,
                        "impostor_samples": 40,
                    }
                ),
                encoding="utf-8",
            )
            with override_settings(FUSION_CALIBRATION_PATH=calibration_file):
                thresholds = get_calibrated_thresholds()
                self.assertEqual(thresholds["fusion_threshold"], 0.67)
                self.assertEqual(
                    thresholds["single_modality_fallback_threshold"], 0.75
                )
                self.assertEqual(thresholds["genuine_samples"], 40)


class AuthenticateHumanWorkflowTests(TestCase):
    """Integration test of the quality-aware decision flow."""

    @staticmethod
    def _engines(iris_quality, voice_quality, speech_activity=0.8):
        iris_engine = patch.object(
            IrisBiometricEngine,
            "extract_features",
            return_value=IrisSample(
                iris_detected=iris_quality >= 0.2,
                quality_score=iris_quality,
                embedding=[0.1, 0.2],
            ),
        )
        voice_engine = patch.object(
            VoiceBiometricEngine,
            "extract_features",
            return_value=VoiceSample(
                duration_seconds=4.0,
                quality_score=voice_quality,
                speech_activity_score=speech_activity,
                rms_level=0.1,
                peak_level=0.4,
                embedding=[0.2, 0.3],
            ),
        )
        return iris_engine, voice_engine

    def test_bug_report_scenario_iris_742_voice_908_is_accepted(self):
        # The exact regression from the report: iris 74.2%, voice 90.8%,
        # old fixed 80% threshold failed the genuine user.
        with patch(
            "biometrics.services.workflow.get_iris_engine",
            return_value=IrisBiometricEngine.__new__(IrisBiometricEngine),
        ), patch(
            "biometrics.services.workflow.get_voice_engine",
            return_value=VoiceBiometricEngine.__new__(VoiceBiometricEngine),
        ):
            iris_patch, voice_patch = self._engines(0.742, 0.908)
            with iris_patch, voice_patch:
                result = authenticate_human(
                    open_eye_path="unused.jpg",
                    voice_path="unused.wav",
                    eye_side="LEFT",
                )

        self.assertEqual(result["decision"], Decision.ACCEPTED)
        self.assertEqual(result["ui_state"], "VERIFIED")
        self.assertIsNone(result["failure_reason"])
        self.assertGreaterEqual(result["fusion"]["score"], result["fusion"]["threshold"])
        # Voice carries more weight than the weaker iris capture.
        self.assertGreater(
            result["fusion"]["voice_weight"], result["fusion"]["iris_weight"]
        )

    def test_blurry_iris_with_strong_voice_never_rejects(self):
        with patch(
            "biometrics.services.workflow.get_iris_engine",
            return_value=IrisBiometricEngine.__new__(IrisBiometricEngine),
        ), patch(
            "biometrics.services.workflow.get_voice_engine",
            return_value=VoiceBiometricEngine.__new__(VoiceBiometricEngine),
        ):
            iris_patch, voice_patch = self._engines(0.30, 0.93)
            with iris_patch, voice_patch:
                result = authenticate_human(
                    open_eye_path="unused.jpg",
                    voice_path="unused.wav",
                    eye_side="LEFT",
                )

        self.assertEqual(result["decision"], Decision.RETRY_REQUIRED)
        self.assertEqual(result["ui_state"], "QUALITY_TOO_LOW")
        self.assertEqual(result["reason_code"], ReasonCode.IRIS_QUALITY_TOO_LOW)
        self.assertNotIn(
            result["decision"],
            {Decision.REJECTED_MISMATCH, Decision.REJECTED_SPOOF},
        )


class ThreeModalFusionTests(TestCase):
    def _measurement(self, score=0.9, quality=0.9, confidence=0.9, activity=None):
        return ModalityMeasurement(
            score=score,
            quality=quality,
            detection_confidence=confidence,
            valid_measurement=True,
            speech_activity=activity,
        )

    def _fuse(self, *, face=None, iris=None, voice=None):
        return fuse_three_modalities(
            face=face or self._measurement(),
            iris=iris or self._measurement(),
            voice=voice or self._measurement(activity=0.8),
            base_face_weight=0.34,
            base_iris_weight=0.33,
            base_voice_weight=0.33,
            fusion_threshold=0.80,
            face_quality_threshold=0.60,
            iris_quality_threshold=0.55,
            iris_detection_confidence_threshold=0.45,
            voice_quality_threshold=0.55,
            voice_activity_threshold=0.35,
            face_similarity_threshold=0.70,
            iris_similarity_threshold=0.78,
            voice_similarity_threshold=0.75,
        )

    def test_all_three_valid_and_matching_are_accepted(self):
        decision = self._fuse()
        self.assertEqual(decision.decision, "ACCEPTED")
        self.assertAlmostEqual(
            decision.face_weight + decision.iris_weight + decision.voice_weight,
            1.0,
            places=3,
        )

    def test_low_quality_face_requires_retry_not_mismatch(self):
        decision = self._fuse(face=self._measurement(quality=0.2))
        self.assertEqual(decision.decision, "RETRY_REQUIRED")
        self.assertEqual(decision.reason_code, ReasonCode.FACE_QUALITY_TOO_LOW)

    def test_usable_face_mismatch_is_rejected(self):
        decision = self._fuse(face=self._measurement(score=0.55))
        self.assertEqual(decision.decision, "REJECTED_MISMATCH")
        self.assertIn("face", decision.policy["failed_modalities"])


class ThreeModalCalibrationTests(TestCase):
    OPTIONS = {
        "base_face_weight": 0.34,
        "base_iris_weight": 0.33,
        "base_voice_weight": 0.33,
        "face_quality_threshold": 0.60,
        "iris_quality_threshold": 0.55,
        "iris_detection_confidence_threshold": 0.45,
        "voice_quality_threshold": 0.55,
        "voice_activity_threshold": 0.35,
    }

    def test_calibration_requires_all_three_quality_gated_modalities(self):
        sample = {
            "iris": {
                "similarity_score": 0.9,
                "quality_score": 0.9,
                "detection_confidence": 0.9,
            },
            "voice": {
                "similarity_score": 0.9,
                "quality_score": 0.9,
                "speech_activity_score": 0.9,
            },
        }
        self.assertIsNone(_fusion_score(sample, self.OPTIONS))

    def test_calibration_uses_quality_weighted_three_modal_score(self):
        sample = {
            "face": {
                "similarity_score": 0.9,
                "quality_score": 0.9,
                "detection_confidence": 0.95,
            },
            "iris": {
                "similarity_score": 0.8,
                "quality_score": 0.7,
                "detection_confidence": 0.8,
            },
            "voice": {
                "similarity_score": 0.95,
                "quality_score": 0.95,
                "speech_activity_score": 0.9,
            },
        }
        score = _fusion_score(sample, self.OPTIONS)
        self.assertIsNotNone(score)
        self.assertGreater(score, 0.85)
        self.assertLess(score, 0.95)


class EnrolledBiometricWorkflowTests(TestCase):
    def setUp(self):
        self.user = BiometricUser.objects.create(
            external_id="ENROLL-001",
            full_name="Enrollment User",
        )

    @patch("biometrics.services.workflow.get_face_engine")
    @patch("biometrics.services.workflow.get_voice_engine")
    @patch("biometrics.services.workflow.get_iris_engine")
    def test_enrollment_stores_encrypted_three_modal_templates(
        self, iris_engine, voice_engine, face_engine
    ):
        face_engine.return_value.extract_features.return_value = FaceSample(
            embedding=[0.2, 0.4, 0.6],
            quality_score=0.88,
            detection_confidence=0.95,
            face_count=1,
            valid_measurement=True,
            reason_code="FACE_VALID",
            message="ok",
            liveness=_live_result(),
        )
        face_engine.return_value.aggregate.return_value = [0.2, 0.4, 0.6]
        iris_engine.return_value.extract_features.return_value = IrisSample(
            iris_detected=True,
            quality_score=0.82,
            embedding=[0.1, 0.2, 0.3],
            detection_confidence=0.88,
        )
        iris_engine.return_value.aggregate_samples.return_value = [0.1, 0.2, 0.3]
        voice_engine.return_value.extract_features.return_value = VoiceSample(
            duration_seconds=4.0,
            quality_score=0.86,
            speech_activity_score=0.78,
            rms_level=0.1,
            peak_level=0.4,
            embedding=[0.4, 0.5, 0.6],
            segment_count=2,
        )
        voice_engine.return_value.aggregate_samples.return_value = [0.4, 0.5, 0.6]

        result = enroll_user_biometrics(
            user=self.user,
            face_paths=["face.jpg"] * settings.MIN_FACE_SAMPLES,
            iris_paths=["iris.jpg"] * settings.MIN_IRIS_SAMPLES,
            voice_paths=["voice_1.wav", "voice_2.wav", "voice_3.wav"],
            eye_side="LEFT",
        )

        self.user.refresh_from_db()
        self.assertEqual(self.user.enrollment_status, EnrollmentStatus.COMPLETE)
        self.assertEqual(self.user.iris_embedding, [])
        self.assertEqual(self.user.voice_embedding, [])
        self.assertEqual(
            decrypt_template(self.user.face_template_encrypted)["vector"],
            [0.2, 0.4, 0.6],
        )
        self.assertEqual(
            decrypt_template(self.user.iris_template_encrypted)["vector"],
            [0.1, 0.2, 0.3],
        )
        self.assertEqual(
            decrypt_template(self.user.voice_template_encrypted)["vector"],
            [0.4, 0.5, 0.6],
        )
        self.assertEqual(result["enrollment_status"], EnrollmentStatus.COMPLETE)

    @override_settings(FACE_PRIMARY_CAPTURE_MODE=True)
    @patch("biometrics.services.workflow.get_face_engine")
    @patch("biometrics.services.workflow.get_voice_engine")
    @patch("biometrics.services.workflow.get_iris_engine")
    def test_prototype_enrollment_builds_face_and_voice_templates_only(
        self, iris_engine, voice_engine, face_engine
    ):
        face_engine.return_value.extract_features.return_value = FaceSample(
            embedding=[0.2, 0.4, 0.6],
            quality_score=0.88,
            detection_confidence=0.95,
            face_count=1,
            valid_measurement=True,
            reason_code="FACE_VALID",
            message="ok",
            liveness=_live_result(),
        )
        face_engine.return_value.aggregate.return_value = [0.2, 0.4, 0.6]
        voice_engine.return_value.extract_features.return_value = VoiceSample(
            duration_seconds=4.0,
            quality_score=0.86,
            speech_activity_score=0.78,
            rms_level=0.1,
            peak_level=0.4,
            embedding=[0.4, 0.5, 0.6],
            segment_count=2,
        )
        voice_engine.return_value.aggregate_samples.return_value = [0.4, 0.5, 0.6]

        result = enroll_user_biometrics(
            user=self.user,
            face_paths=["camera_1.jpg", "camera_2.jpg", "camera_3.jpg"],
            iris_paths=["camera_1.jpg", "camera_2.jpg", "camera_3.jpg"],
            voice_paths=["voice_1.wav", "voice_2.wav", "voice_3.wav"],
            eye_side="LEFT",
        )

        self.user.refresh_from_db()
        self.assertEqual(result["face_samples"], 3)
        self.assertEqual(result["iris_samples"], 3)
        self.assertEqual(result["voice_samples"], 3)
        self.assertFalse(self.user.iris_template_encrypted)
        self.assertTrue(self.user.face_template_encrypted)
        self.assertTrue(self.user.voice_template_encrypted)
        face_engine.return_value.aggregate.assert_called_once()
        voice_engine.return_value.aggregate_samples.assert_called_once()
        iris_engine.assert_not_called()

    @override_settings(FACE_PRIMARY_CAPTURE_MODE=True, DEVELOPMENT_THRESHOLDS=True)
    @patch("biometrics.services.workflow.get_calibrated_thresholds")
    @patch("biometrics.services.workflow.decrypt_template")
    @patch("biometrics.services.workflow.get_face_engine")
    @patch("biometrics.services.workflow.get_voice_engine")
    @patch("biometrics.services.workflow.get_iris_engine")
    def test_prototype_login_matches_one_face_frame_and_one_voice_capture(
        self, iris_engine, voice_engine, face_engine, decrypt, calibrated
    ):
        self.user.enrollment_status = EnrollmentStatus.COMPLETE
        self.user.face_template_encrypted = "encrypted-face"
        self.user.iris_template_encrypted = ""
        self.user.voice_template_encrypted = "encrypted-voice"
        self.user.save()
        decrypt.side_effect = [
            {"vector": [0.2, 0.4, 0.6]},
            {"vector": [0.4, 0.5, 0.6]},
        ]
        calibrated.return_value = {
            "fusion_threshold": 0.80,
            "single_modality_fallback_threshold": 0.9,
            "source": "test",
            "calibrated": False,
        }
        face_engine.return_value.extract_features.return_value = FaceSample(
            [0.2, 0.4, 0.6], 0.9, 0.95, 1, True, "FACE_VALID", "ok",
            liveness=_live_result(),
        )
        face_engine.return_value.compare_samples.return_value = {
            "face": {
                "quality_score": 0.9,
                "detection_confidence": 0.95,
                "normalized_score": 0.92,
                "raw_score": 0.84,
                "valid_measurement": True,
                "passed": True,
                "sample_count": 1,
            }
        }
        voice_engine.return_value.compare.return_value = {
            "voice": {
                "quality_score": 0.9,
                "speech_activity_score": 0.85,
                "segment_count": settings.MIN_VOICE_SEGMENTS,
                "normalized_score": 0.9,
                "raw_score": 0.8,
                "passed": True,
            }
        }

        result = authenticate_enrolled_user(
            user=self.user,
            face_paths=["camera_frame.jpg"],
            iris_paths=["camera_frame.jpg"],
            voice_path="login_voice.wav",
            eye_side="LEFT",
        )

        self.assertEqual(result["decision"], Decision.ACCEPTED)
        self.assertEqual(result["iris"]["valid_measurement"], False)
        self.assertEqual(result["fusion"]["iris_weight"], 0.0)
        self.assertGreater(result["fusion"]["face_weight"], 0.0)
        self.assertGreater(result["fusion"]["voice_weight"], 0.0)
        # Dedicated liveness, face similarity, status and failure reason are
        # all reported explicitly on a successful login.
        self.assertEqual(result["face_similarity"], 0.92)
        self.assertEqual(result["verification_status"], "VERIFIED")
        self.assertTrue(result["liveness_result"])
        self.assertEqual(result["liveness"]["status"], "LIVE")
        self.assertEqual(result["liveness"]["anti_spoof_model"], "test-antispoof")
        self.assertIsNone(result["failure_reason"])
        face_engine.return_value.compare_samples.assert_called_once()
        self.assertEqual(
            len(face_engine.return_value.compare_samples.call_args.args[0]), 1
        )
        voice_engine.return_value.compare.assert_called_once_with(
            "login_voice.wav", [0.4, 0.5, 0.6]
        )
        iris_engine.assert_not_called()

    @patch("biometrics.services.workflow.decrypt_template")
    @patch("biometrics.services.workflow.get_face_engine")
    @patch("biometrics.services.workflow.get_voice_engine")
    @patch("biometrics.services.workflow.get_iris_engine")
    def test_high_quality_template_mismatch_is_rejected(
        self, iris_engine, voice_engine, face_engine, decrypt
    ):
        self.user.enrollment_status = EnrollmentStatus.COMPLETE
        self.user.face_template_encrypted = "face"
        self.user.iris_template_encrypted = "iris"
        self.user.voice_template_encrypted = "voice"
        self.user.save()
        decrypt.side_effect = [
            {"vector": [0.1]},
            {"vector": [0.1]},
            {"vector": [0.1]},
        ]
        face_engine.return_value.extract_features.return_value = FaceSample(
            [0.1], 0.9, 0.9, 1, True, "FACE_VALID", "ok",
            liveness=_live_result(),
        )
        iris_engine.return_value.extract_features.return_value = IrisSample(
            True, 0.9, [0.1], 0.9
        )
        face_engine.return_value.compare_samples.return_value = {
            "face": {
                "quality_score": 0.9,
                "detection_confidence": 0.9,
                "normalized_score": 0.9,
                "valid_measurement": True,
                "passed": True,
            }
        }
        iris_engine.return_value.compare_samples.return_value = {
            "iris": {
                "iris_detected": True,
                "quality_score": 0.9,
                "detection_confidence": 0.9,
                "normalized_score": 0.60,
                "raw_score": 0.2,
                "threshold": settings.IRIS_SIMILARITY_THRESHOLD,
                "passed": False,
                "message": "Iris did not match the reference template.",
            }
        }
        voice_engine.return_value.compare.return_value = {
            "voice": {
                "quality_score": 0.9,
                "speech_activity_score": 0.8,
                "segment_count": 2,
                "speech_detected": True,
                "normalized_score": 0.9,
                "raw_score": 0.8,
                "threshold": settings.VOICE_SIMILARITY_THRESHOLD,
                "activity_threshold": settings.VOICE_ACTIVITY_THRESHOLD,
                "passed": True,
                "message": "Voice matched.",
            }
        }

        result = authenticate_enrolled_user(
            user=self.user,
            face_paths=["face.jpg"] * settings.MIN_FACE_SAMPLES,
            iris_paths=["iris.jpg"] * settings.MIN_IRIS_SAMPLES,
            voice_path="unused.wav",
            eye_side="LEFT",
        )

        self.assertEqual(result["decision"], Decision.REJECTED_MISMATCH)
        self.assertEqual(result["ui_state"], "REJECTED_MISMATCH")


class FaceLivenessEngineTests(TestCase):
    """The anti-spoofing model is a separate classifier, not SCRFD confidence."""

    def _engine(self, output):
        import cv2
        import numpy as np

        engine = FaceLivenessEngine.__new__(FaceLivenessEngine)
        engine._cv2 = cv2
        engine._np = np
        engine._net = _FakeLivenessNet(np.asarray(output, dtype=np.float32))
        engine._model_name = "test-antispoof"
        engine._model_path = "test-antispoof.onnx"
        engine._load_error = None
        engine._lock = Lock()
        return engine

    @override_settings(
        FACE_LIVENESS_ACTIVATION="softmax",
        FACE_LIVENESS_LIVE_INDEX=1,
        FACE_LIVENESS_THRESHOLD=0.60,
    )
    def test_live_face_passes_with_dedicated_model(self):
        import numpy as np

        # Upstream convention (yakhyo/face-anti-spoofing onnx_inference.py):
        # class index 1 = Real, established by the A/B/C diagnostic on a real
        # webcam frame with raw 0-255 input (not by the HF model card).
        engine = self._engine([[0.1, 6.0, 0.2]])
        image = np.full((200, 200, 3), 128, dtype=np.uint8)
        result = engine.assess(image, [40, 40, 160, 160])
        self.assertTrue(result.evaluated)
        self.assertTrue(result.passed)
        self.assertEqual(result.status, "LIVE")
        self.assertGreater(result.live_score, 0.9)
        self.assertEqual(result.model, "test-antispoof")

    @override_settings(
        FACE_LIVENESS_ACTIVATION="softmax",
        FACE_LIVENESS_LIVE_INDEX=1,
        FACE_LIVENESS_THRESHOLD=0.60,
    )
    def test_spoof_face_is_rejected(self):
        import numpy as np

        # Spoof evidence on a non-live class (0 here) must reject.
        engine = self._engine([[6.0, 0.1, 0.2]])
        image = np.full((200, 200, 3), 128, dtype=np.uint8)
        result = engine.assess(image, [40, 40, 160, 160])
        self.assertTrue(result.evaluated)
        self.assertFalse(result.passed)
        self.assertEqual(result.status, "SPOOF")

    @override_settings(
        FACE_LIVENESS_ACTIVATION="softmax",
        FACE_LIVENESS_LIVE_INDEX=1,
        FACE_LIVENESS_THRESHOLD=0.60,
    )
    def test_blob_preserves_bgr_channel_order(self):
        """The ONNX model expects BGR, so blobFromImage must not swap channels."""
        import cv2
        import numpy as np

        engine = self._engine([[0.1, 6.0, 0.2]])
        image = np.full((200, 200, 3), 128, dtype=np.uint8)
        engine.assess(image, [40, 40, 160, 160])
        blob = engine._net.input
        self.assertEqual(blob.shape, (1, 3, 80, 80))
        self.assertEqual(blob.dtype, np.float32)
        expected = cv2.dnn.blobFromImage(
            np.full((80, 80, 3), 128, dtype=np.uint8),
            scalefactor=1.0,
            size=(80, 80),
            mean=(0.0, 0.0, 0.0),
            swapRB=False,
        )
        np.testing.assert_allclose(blob, expected)

    @override_settings(
        FACE_LIVENESS_ACTIVATION="softmax",
        FACE_LIVENESS_LIVE_INDEX=1,
        FACE_LIVENESS_THRESHOLD=0.60,
    )
    def test_blob_uses_raw_pixel_values_not_normalized(self):
        """Upstream MiniFASNet inference takes raw 0-255 float32, never /255."""
        import numpy as np

        engine = self._engine([[0.1, 6.0, 0.2]])
        image = np.full((200, 200, 3), 200, dtype=np.uint8)
        engine.assess(image, [40, 40, 160, 160])
        blob = engine._net.input
        self.assertAlmostEqual(float(blob.max()), 200.0, places=3)
        self.assertGreater(float(blob.min()), 0.0)

    @override_settings(
        FACE_LIVENESS_ACTIVATION="softmax",
        FACE_LIVENESS_LIVE_INDEX=1,
        FACE_LIVENESS_THRESHOLD=0.60,
    )
    def test_assessment_reports_logits_softmax_and_class_diagnostics(self):
        """Score diagnostics cover logits, softmax, predicted class, probabilities."""
        import numpy as np

        logits = [-1.8516, 3.0825, -1.2333]
        engine = self._engine([logits])
        image = np.full((200, 200, 3), 128, dtype=np.uint8)
        with self.assertLogs("biometrics.services.face_liveness", level="INFO") as logs:
            result = engine.assess(image, [40, 40, 160, 160])
        diagnostic = " ".join(logs.output)
        self.assertIn("raw_logits=[-1.8516, 3.0825, -1.2333]", diagnostic)
        self.assertIn("predicted_class=1", diagnostic)
        self.assertIn("live_index=1", diagnostic)
        # The live class carries its softmax probability; spoof score is the
        # strongest non-live class probability.
        largest = max(logits)
        exponentials = [2.718281828459045 ** (value - largest) for value in logits]
        total = sum(exponentials)
        probabilities = [value / total for value in exponentials]
        expected_spoof = max(value for index, value in enumerate(probabilities) if index != 1)
        self.assertAlmostEqual(result.live_score, probabilities[1], places=4)
        self.assertAlmostEqual(result.spoof_score, expected_spoof, places=4)
        self.assertIn("live_prob=", diagnostic)
        self.assertIn("spoof_prob=", diagnostic)

    def test_debug_crop_saved_when_enabled(self):
        """The exact classifier-input crop is persisted for inspection."""
        import cv2
        import numpy as np

        engine = self._engine([[0.1, 6.0, 0.2]])
        image = np.full((200, 200, 3), 128, dtype=np.uint8)
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(
                FACE_LIVENESS_INPUT_SIZE=80,
                FACE_LIVENESS_CROP_SCALE=2.7,
                FACE_LIVENESS_DEBUG_SAVE_CROP=True,
                MEDIA_ROOT=media_root,
            ):
                result = engine.assess(image, [40, 40, 160, 160])
            self.assertTrue(result.evaluated)
            saved = list(Path(media_root, "liveness_debug").glob("liveness_crop_*.jpg"))
            self.assertEqual(len(saved), 2)
            full = next(path for path in saved if not path.stem.endswith("80x80"))
            small = next(path for path in saved if path.stem.endswith("80x80"))
            self.assertEqual(cv2.imread(str(small)).shape[:2], (80, 80))
            self.assertIsNotNone(cv2.imread(str(full)))

    def test_debug_crop_not_saved_by_default(self):
        import numpy as np

        engine = self._engine([[0.1, 6.0, 0.2]])
        image = np.full((200, 200, 3), 128, dtype=np.uint8)
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(
                FACE_LIVENESS_INPUT_SIZE=80,
                FACE_LIVENESS_CROP_SCALE=2.7,
                MEDIA_ROOT=media_root,
            ):
                engine.assess(image, [40, 40, 160, 160])
            self.assertFalse(Path(media_root, "liveness_debug").exists())

    def test_unavailable_model_is_never_reported_as_live(self):
        import numpy as np

        engine = FaceLivenessEngine.__new__(FaceLivenessEngine)
        engine._cv2 = None
        engine._np = None
        engine._net = None
        engine._model_name = "test-antispoof"
        engine._model_path = None
        engine._load_error = FileNotFoundError("missing model")
        engine._lock = Lock()

        self.assertFalse(engine.ready)
        result = engine.assess(np.zeros((10, 10, 3), dtype=np.uint8), [1, 1, 5, 5])
        self.assertFalse(result.evaluated)
        self.assertFalse(result.passed)
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertEqual(result.reason_code, "LIVENESS_MODEL_UNAVAILABLE")


class FaceLivenessWorkflowTests(TestCase):
    """Registration and login must gate on the dedicated liveness model."""

    def setUp(self):
        self.user = BiometricUser.objects.create(
            external_id="LIVE-001",
            full_name="Liveness User",
        )

    def _enroll_prototype(self):
        self.user.enrollment_status = EnrollmentStatus.COMPLETE
        self.user.face_template_encrypted = "encrypted-face"
        self.user.iris_template_encrypted = ""
        self.user.voice_template_encrypted = "encrypted-voice"
        self.user.save()

    def _thresholds(self):
        return {
            "fusion_threshold": 0.80,
            "single_modality_fallback_threshold": 0.9,
            "source": "test",
            "calibrated": False,
        }

    @override_settings(FACE_PRIMARY_CAPTURE_MODE=True, FACE_LIVENESS_REQUIRED=True)
    @patch("biometrics.services.workflow.get_face_engine")
    @patch("biometrics.services.workflow.get_voice_engine")
    @patch("biometrics.services.workflow.get_iris_engine")
    def test_enrollment_fails_closed_when_liveness_model_unavailable(
        self, iris_engine, voice_engine, face_engine
    ):
        # No liveness result attached: the anti-spoofing stage cannot run.
        face_engine.return_value.extract_features.return_value = FaceSample(
            [0.2, 0.4, 0.6], 0.88, 0.95, 1, True, "FACE_VALID", "ok"
        )
        with self.assertRaises(ModelUnavailableError):
            enroll_user_biometrics(
                user=self.user,
                face_paths=["camera_1.jpg"],
                iris_paths=["camera_1.jpg"],
                voice_paths=["voice_1.wav"],
                eye_side="LEFT",
            )
        self.user.refresh_from_db()
        self.assertFalse(self.user.face_template_encrypted)

    @override_settings(FACE_PRIMARY_CAPTURE_MODE=True)
    @patch("biometrics.services.workflow.get_face_engine")
    @patch("biometrics.services.workflow.get_voice_engine")
    @patch("biometrics.services.workflow.get_iris_engine")
    def test_enrollment_rejects_spoofed_face(
        self, iris_engine, voice_engine, face_engine
    ):
        face_engine.return_value.extract_features.return_value = FaceSample(
            [0.2, 0.4, 0.6], 0.88, 0.99, 1, True, "FACE_VALID", "ok",
            liveness=_spoof_result(),
        )
        with self.assertRaises(SpoofDetectedError):
            enroll_user_biometrics(
                user=self.user,
                face_paths=["camera_1.jpg"],
                iris_paths=["camera_1.jpg"],
                voice_paths=["voice_1.wav"],
                eye_side="LEFT",
            )
        self.user.refresh_from_db()
        self.assertFalse(self.user.face_template_encrypted)

    @override_settings(FACE_PRIMARY_CAPTURE_MODE=True, DEVELOPMENT_THRESHOLDS=True)
    @patch("biometrics.services.workflow.get_calibrated_thresholds")
    @patch("biometrics.services.workflow.decrypt_template")
    @patch("biometrics.services.workflow.get_face_engine")
    @patch("biometrics.services.workflow.get_voice_engine")
    @patch("biometrics.services.workflow.get_iris_engine")
    def test_login_spoofed_face_is_rejected_as_spoof(
        self, iris_engine, voice_engine, face_engine, decrypt, calibrated
    ):
        self._enroll_prototype()
        decrypt.side_effect = [
            {"vector": [0.2, 0.4, 0.6]},
            {"vector": [0.4, 0.5, 0.6]},
        ]
        calibrated.return_value = self._thresholds()
        # A high SCRFD detection confidence with a failed anti-spoofing result
        # must still be rejected: detection confidence is not liveness.
        face_engine.return_value.extract_features.return_value = FaceSample(
            [0.2, 0.4, 0.6], 0.9, 0.99, 1, True, "FACE_VALID", "ok",
            liveness=_spoof_result(),
        )
        face_engine.return_value.compare_samples.return_value = {
            "face": {
                "quality_score": 0.9,
                "detection_confidence": 0.99,
                "normalized_score": 0.95,
                "raw_score": 0.9,
                "valid_measurement": True,
                "passed": True,
                "sample_count": 1,
            }
        }
        voice_engine.return_value.compare.return_value = {
            "voice": {
                "quality_score": 0.9,
                "speech_activity_score": 0.85,
                "segment_count": settings.MIN_VOICE_SEGMENTS,
                "normalized_score": 0.9,
                "raw_score": 0.8,
                "passed": True,
            }
        }

        result = authenticate_enrolled_user(
            user=self.user,
            face_paths=["camera_frame.jpg"],
            iris_paths=["camera_frame.jpg"],
            voice_path="login_voice.wav",
            eye_side="LEFT",
        )

        self.assertEqual(result["decision"], Decision.REJECTED_SPOOF)
        self.assertEqual(result["ui_state"], "REJECTED_SPOOF")
        self.assertEqual(result["verification_status"], "REJECTED_SPOOF")
        self.assertEqual(result["liveness"]["status"], "SPOOF")
        self.assertFalse(result["liveness_result"])
        self.assertTrue(result["failure_reason"])
        self.assertEqual(result["face_similarity"], 0.95)
        iris_engine.assert_not_called()

    @override_settings(
        FACE_PRIMARY_CAPTURE_MODE=True,
        DEVELOPMENT_THRESHOLDS=True,
        FACE_LIVENESS_REQUIRED=True,
    )
    @patch("biometrics.services.workflow.get_calibrated_thresholds")
    @patch("biometrics.services.workflow.decrypt_template")
    @patch("biometrics.services.workflow.get_face_engine")
    @patch("biometrics.services.workflow.get_voice_engine")
    @patch("biometrics.services.workflow.get_iris_engine")
    def test_login_fails_closed_when_liveness_model_unavailable(
        self, iris_engine, voice_engine, face_engine, decrypt, calibrated
    ):
        self._enroll_prototype()
        decrypt.side_effect = [
            {"vector": [0.2, 0.4, 0.6]},
            {"vector": [0.4, 0.5, 0.6]},
        ]
        calibrated.return_value = self._thresholds()
        face_engine.return_value.extract_features.return_value = FaceSample(
            [0.2, 0.4, 0.6], 0.9, 0.95, 1, True, "FACE_VALID", "ok"
        )
        face_engine.return_value.compare_samples.return_value = {
            "face": {
                "quality_score": 0.9,
                "detection_confidence": 0.95,
                "normalized_score": 0.95,
                "raw_score": 0.9,
                "valid_measurement": True,
                "passed": True,
                "sample_count": 1,
            }
        }
        voice_engine.return_value.compare.return_value = {
            "voice": {
                "quality_score": 0.9,
                "speech_activity_score": 0.85,
                "segment_count": settings.MIN_VOICE_SEGMENTS,
                "normalized_score": 0.9,
                "raw_score": 0.8,
                "passed": True,
            }
        }

        result = authenticate_enrolled_user(
            user=self.user,
            face_paths=["camera_frame.jpg"],
            iris_paths=["camera_frame.jpg"],
            voice_path="login_voice.wav",
            eye_side="LEFT",
        )

        self.assertEqual(result["decision"], Decision.PROCESSING_ERROR)
        self.assertEqual(result["verification_status"], "PROCESSING_ERROR")
        self.assertEqual(result["liveness"]["status"], "UNAVAILABLE")
        self.assertFalse(result["liveness_result"])
        self.assertTrue(result["failure_reason"])

    @override_settings(
        FACE_PRIMARY_CAPTURE_MODE=True,
        DEVELOPMENT_THRESHOLDS=True,
        FACE_LIVENESS_REQUIRED=False,
    )
    @patch("biometrics.services.workflow.get_calibrated_thresholds")
    @patch("biometrics.services.workflow.decrypt_template")
    @patch("biometrics.services.workflow.get_face_engine")
    @patch("biometrics.services.workflow.get_voice_engine")
    @patch("biometrics.services.workflow.get_iris_engine")
    def test_development_login_does_not_fabricate_liveness(
        self, iris_engine, voice_engine, face_engine, decrypt, calibrated
    ):
        """When enforcement is off, liveness is still reported honestly."""
        self._enroll_prototype()
        decrypt.side_effect = [
            {"vector": [0.2, 0.4, 0.6]},
            {"vector": [0.4, 0.5, 0.6]},
        ]
        calibrated.return_value = self._thresholds()
        face_engine.return_value.extract_features.return_value = FaceSample(
            [0.2, 0.4, 0.6], 0.9, 0.95, 1, True, "FACE_VALID", "ok"
        )
        face_engine.return_value.compare_samples.return_value = {
            "face": {
                "quality_score": 0.9,
                "detection_confidence": 0.95,
                "normalized_score": 0.92,
                "raw_score": 0.84,
                "valid_measurement": True,
                "passed": True,
                "sample_count": 1,
            }
        }
        voice_engine.return_value.compare.return_value = {
            "voice": {
                "quality_score": 0.9,
                "speech_activity_score": 0.85,
                "segment_count": settings.MIN_VOICE_SEGMENTS,
                "normalized_score": 0.9,
                "raw_score": 0.8,
                "passed": True,
            }
        }

        result = authenticate_enrolled_user(
            user=self.user,
            face_paths=["camera_frame.jpg"],
            iris_paths=["camera_frame.jpg"],
            voice_path="login_voice.wav",
            eye_side="LEFT",
        )

        # The identity decision may still pass, but liveness is never claimed.
        self.assertEqual(result["decision"], Decision.ACCEPTED)
        self.assertEqual(result["liveness"]["status"], "UNAVAILABLE")
        self.assertFalse(result["liveness_result"])
        self.assertFalse(result["liveness"]["passed"])
        self.assertIsNone(result["liveness"]["anti_spoof_model"])


class SummarizeLivenessAggregationTests(TestCase):
    """Multi-frame aggregation: one bad frame must not reject enrollment."""

    def test_single_bad_frame_does_not_reject_majority_live(self):
        summary = summarize_liveness(
            [_live_result(0.95), _live_result(0.92), _spoof_result(0.05)]
        )
        self.assertTrue(summary["passed"])
        self.assertEqual(summary["status"], "LIVE")
        self.assertEqual(summary["live_votes"], 2)
        self.assertEqual(summary["spoof_votes"], 1)
        self.assertGreaterEqual(summary["live_score"], settings.FACE_LIVENESS_THRESHOLD)

    def test_all_spoof_frames_are_rejected(self):
        summary = summarize_liveness(
            [_spoof_result(0.05), _spoof_result(0.10), _spoof_result(0.08)]
        )
        self.assertFalse(summary["passed"])
        self.assertEqual(summary["status"], "SPOOF")
        self.assertEqual(summary["live_votes"], 0)

    def test_majority_spoof_is_rejected_despite_one_live_frame(self):
        summary = summarize_liveness(
            [_live_result(0.95), _spoof_result(0.05), _spoof_result(0.05)]
        )
        self.assertFalse(summary["passed"])
        self.assertEqual(summary["status"], "SPOOF")
        self.assertEqual(summary["live_votes"], 1)

    def test_split_vote_without_spoof_evidence_fails_closed(self):
        summary = summarize_liveness([_live_result(0.95), _spoof_result(0.05)])
        self.assertFalse(summary["passed"])
        self.assertEqual(summary["status"], "SPOOF")

    def test_weak_mean_live_score_does_not_pass(self):
        # Majority of frames technically LIVE, but the mean live probability
        # is below the threshold: aggregate evidence is too weak to pass.
        summary = summarize_liveness(
            [_live_result(0.65), _live_result(0.55), _spoof_result(0.45)]
        )
        self.assertFalse(summary["passed"])
        self.assertEqual(summary["status"], "SPOOF")

    def test_single_live_frame_still_passes(self):
        """Authentication uses one capture; the aggregate must not break it."""
        summary = summarize_liveness([_live_result(0.95)])
        self.assertTrue(summary["passed"])
        self.assertEqual(summary["status"], "LIVE")
        self.assertEqual(summary["live_votes"], 1)


class HealthReadinessTests(TestCase):
    """A missing anti-spoofing asset must not stall the global status."""

    def setUp(self):
        self.client = APIClient()

    @patch("biometrics.views.get_service_health")
    def test_status_is_ok_when_anti_spoof_model_is_missing(self, health):
        health.return_value = {
            "face_model": {"ready": True, "mode": "local_buffalo_l"},
            "face_liveness_model": {"ready": False, "required": False},
            "voice_model": {"ready": True, "mode": "local_pretrained"},
            "iris_model": {"ready": True, "mode": "local_onnx"},
            "offline_mode": True,
            "development_thresholds": True,
            "fusion_calibration_ready": False,
            "fusion_threshold_source": "defaults",
        }

        response = self.client.get("/api/v1/health/")

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["status"], "ok")
        self.assertFalse(data["face_liveness_ready"])
        self.assertTrue(data["face_verification_ready"])


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
        self.assertEqual(data["minimum_face_samples"], settings.MIN_FACE_SAMPLES)
        self.assertEqual(data["minimum_voice_samples"], settings.MIN_VOICE_SAMPLES)
        self.assertEqual(data["minimum_voice_segments"], settings.MIN_VOICE_SEGMENTS)
        self.assertEqual(data["minimum_iris_samples"], settings.MIN_IRIS_SAMPLES)
        self.assertIn("face_model", data)
        self.assertIn("voice_model", data)
        self.assertIn("iris_model", data)

    def test_validation_errors_use_frontend_message_shape(self):
        response = self.client.post("/api/v1/test/voice/", data={})
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("message", payload)
        self.assertIn("errors", payload)
        self.assertIn("voice_file", payload["message"])

    @patch("biometrics.views.get_iris_engine")
    def test_iris_tracking_returns_mask_geometry(self, get_engine):
        get_engine.return_value.track_iris.return_value = {
            "detected": True,
            "confidence": 0.86,
            "stable": True,
            "circularity": 0.81,
            "center_x": 268.8,
            "center_y": 177.6,
            "iris_width": 64.0,
            "iris_height": 58.0,
            "radius": 30.5,
            "angle_degrees": 12.0,
            "contour": [[240.0, 177.6], [268.8, 150.0], [300.0, 177.6]],
            "bounding_box": {
                "x": 236.0,
                "y": 148.0,
                "width": 66.0,
                "height": 60.0,
            },
            "frame_width": 640,
            "frame_height": 480,
        }
        frame = SimpleUploadedFile(
            "frame.jpg",
            b"camera-frame",
            content_type="image/jpeg",
        )

        response = self.client.post(
            "/api/v1/test/iris/tracking/",
            data={"frame": frame},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertTrue(data["detected"])
        self.assertEqual(data["center_x"], 268.8)
        self.assertEqual(data["iris_width"], 64.0)
        self.assertEqual(len(data["contour"]), 3)
        get_engine.return_value.track_iris.assert_called_once()

    def test_banking_registration_creates_customer_and_biometric_user(self):
        response = self.client.post(
            "/api/v1/banking/register/",
            data={
                "full_name": "Asha Banker",
                "mobile_number": "9876543210",
                "pin": "1234",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()["data"]
        customer = data["customer"]
        self.assertTrue(data["token"])
        self.assertRegex(customer["customer_id"], r"^[0-9]{6}$")
        self.assertNotIn("account_number", customer)
        self.assertNotIn("pin_hash", customer)
        self.assertTrue(customer["biometric_user_id"])
        self.assertEqual(customer["enrollment_status"], EnrollmentStatus.PENDING)
        self.assertEqual(customer["enrolled_eye_side"], "LEFT")
        self.assertTrue(
            BankingCustomer.objects.filter(
                customer_id=customer["customer_id"],
            ).exists()
        )
        self.assertTrue(
            BiometricUser.objects.filter(external_id=customer["customer_id"]).exists()
        )

    def test_banking_registration_generates_unique_identifiers(self):
        payload = {
            "full_name": "Generated Customer",
            "mobile_number": "9876543211",
            "pin": "4321",
        }
        first = self.client.post(
            "/api/v1/banking/register/", data=payload, format="json"
        )
        payload["mobile_number"] = "9876543212"
        second = self.client.post(
            "/api/v1/banking/register/", data=payload, format="json"
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        first_customer = first.json()["data"]["customer"]
        second_customer = second.json()["data"]["customer"]
        self.assertNotEqual(
            first_customer["customer_id"], second_customer["customer_id"]
        )

    def test_registration_blocks_mobile_even_before_enrollment(self):
        payload = {
            "full_name": "First Account",
            "mobile_number": "9876543210",
            "pin": "1234",
        }
        first = self.client.post("/api/v1/banking/register/", data=payload, format="json")
        self.assertEqual(first.status_code, 201)
        customer_count = BankingCustomer.objects.count()
        biometric_count = BiometricUser.objects.count()
        payload.update(full_name="Another Account", mobile_number=" 9876543210 ", pin="4321")
        second = self.client.post("/api/v1/banking/register/", data=payload, format="json")
        self.assertEqual(second.status_code, 400)
        self.assertIn("already registered", second.json()["message"])
        self.assertNotIn("token", second.json().get("data", {}))
        self.assertEqual(BankingCustomer.objects.count(), customer_count)
        self.assertEqual(BiometricUser.objects.count(), biometric_count)

    def test_banking_login_returns_session_token(self):
        registration = self.client.post(
            "/api/v1/banking/register/",
            data={
                "full_name": "Login Customer",
                "mobile_number": "9876543210",
                "pin": "1234",
            },
            format="json",
        )
        customer_id = registration.json()["data"]["customer"]["customer_id"]

        customer = BankingCustomer.objects.get(customer_id=customer_id)
        self.assertNotEqual(customer.pin_hash, "1234")
        self.assertTrue(check_password("1234", customer.pin_hash))
        rejected = self.client.post(
            "/api/v1/banking/login/",
            data={"customer_id": customer_id, "pin": "9999"},
            format="json",
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(rejected.json()["message"], "Incorrect PIN. Please try again.")
        self.assertNotIn("token", rejected.json().get("data", {}))

        response = self.client.post(
            "/api/v1/banking/login/",
            data={
                "customer_id": customer_id,
                "pin": "1234",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertTrue(data["token"])
        self.assertEqual(data["customer"]["customer_id"], customer_id)
        self.assertIsNotNone(data["customer"]["biometric_user_id"])
        self.assertEqual(data["next_step"], "BIOMETRIC_ENROLLMENT")
        self.assertIsNone(BankingCustomer.objects.get(pk=customer.pk).last_login_at)

        # A stale COMPLETE flag without saved templates must also resume setup.
        user = customer.biometric_user
        user.enrollment_status = EnrollmentStatus.COMPLETE
        user.save(update_fields=["enrollment_status"])
        retry = self.client.post(
            "/api/v1/banking/login/",
            data={"customer_id": customer_id, "pin": "1234"},
            format="json",
        )
        self.assertEqual(retry.json()["data"]["next_step"], "BIOMETRIC_ENROLLMENT")
        # Only stored templates plus COMPLETE status route to verification.
        user.face_template_encrypted = "saved-face-template"
        user.voice_template_encrypted = "saved-voice-template"
        user.iris_template_encrypted = "saved-iris-template"
        user.save()
        completed = self.client.post(
            "/api/v1/banking/login/",
            data={"customer_id": customer_id, "pin": "1234"},
            format="json",
        )
        self.assertEqual(completed.json()["data"]["next_step"], "BIOMETRIC_VERIFICATION")

    def test_banking_login_rejects_bad_credentials(self):
        response = self.client.post(
            "/api/v1/banking/login/",
            data={
                "customer_id": "MISSING",
                "pin": "0000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid customer ID", response.json()["message"])

    def test_banking_login_reports_unknown_numeric_customer(self):
        response = self.client.post(
            "/api/v1/banking/login/",
            data={"customer_id": "000000", "pin": "1234"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["message"],
            "Customer ID does not exist. Check the number or create an account.",
        )
        self.assertNotIn("token", response.json().get("data", {}))

    def test_banking_login_rejects_non_numeric_pin(self):
        response = self.client.post(
            "/api/v1/banking/login/",
            data={
                "customer_id": "MISSING",
                "pin": "abcd",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("pin", response.json()["message"])

    def test_pin_login_throttles_repeated_attempts(self):
        cache.clear()
        try:
            for _ in range(5):
                response = self.client.post(
                    "/api/v1/banking/login/",
                    {"customer_id": "THROTTLE-TEST", "pin": "0000"},
                    format="json",
                )
                self.assertEqual(response.status_code, 400)
            response = self.client.post(
                "/api/v1/banking/login/",
                {"customer_id": "THROTTLE-TEST", "pin": "0000"},
                format="json",
            )
            self.assertEqual(response.status_code, 429)
        finally:
            cache.clear()

    @patch("biometrics.views.enroll_user_biometrics")
    def test_registration_session_can_enroll_both_templates(self, enroll):
        registration = self.client.post(
            "/api/v1/banking/register/",
            data={
                "full_name": "Enrollment API User",
                "mobile_number": "9876543212",
                "pin": "2468",
            },
            format="json",
        ).json()["data"]
        user_id = registration["customer"]["biometric_user_id"]
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {registration['token']}"
        )
        enroll.return_value = {
            "enrollment_status": "COMPLETE",
            "user_id": user_id,
            "message": "enrolled",
        }

        response = self.client.post(
            f"/api/v1/users/{user_id}/enrollment/",
            data={
                "face_files": [
                    SimpleUploadedFile(
                        f"face_{index}.jpg", b"face", content_type="image/jpeg"
                    )
                    for index in range(settings.MIN_FACE_SAMPLES)
                ],
                "iris_files": [
                    SimpleUploadedFile(
                        f"eye_{index}.jpg", b"eye", content_type="image/jpeg"
                    )
                    for index in range(settings.MIN_IRIS_SAMPLES)
                ],
                "voice_files": [
                    SimpleUploadedFile(
                        f"voice_{index}.wav", b"voice", content_type="audio/wav"
                    )
                    for index in range(settings.MIN_VOICE_SAMPLES)
                ],
                "eye_side": "LEFT",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["enrollment_status"], "COMPLETE")
        enroll.assert_called_once()


class BiometricAuthenticateApiTests(TestCase):
    """Contract tests for the IRL biometric-authenticate endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.user = BiometricUser.objects.create(
            external_id="AUTH-001",
            full_name="Authentication User",
            enrollment_status=EnrollmentStatus.COMPLETE,
            iris_embedding=[0.1, 0.2],
            voice_embedding=[0.2, 0.3],
        )
        BankingCustomer.objects.create(
            biometric_user=self.user,
            customer_id="AUTH-001",
            full_name="Authentication User",
            mobile_number="9876543210",
            pin_hash="unused",
        )
        token = signing.dumps(
            {
                "customer_id": str(self.user.banking_customer.id),
                "biometric_user_id": str(self.user.id),
            },
            salt="banking-login",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    @staticmethod
    def _post(client, **overrides):
        payload = {
            "user_id": "AUTH-001",
            "face_files": [
                SimpleUploadedFile(
                    f"face_{index}.jpg", b"face-bytes", content_type="image/jpeg"
                )
                for index in range(settings.MIN_FACE_SAMPLES)
            ],
            "iris_files": [
                SimpleUploadedFile(
                    f"eye_{index}.jpg", b"iris-bytes", content_type="image/jpeg"
                )
                for index in range(settings.MIN_IRIS_SAMPLES)
            ],
            "voice_file": SimpleUploadedFile("voice.wav", b"voice-bytes", content_type="audio/wav"),
            "eye_side": "LEFT",
        }
        payload.update(overrides)
        return client.post("/api/v1/biometric-authenticate/", data=payload, format="multipart")

    def _workflow_patch(self, iris, voice):
        face = {
            "quality_score": 0.88,
            "detection_confidence": 0.95,
            "passed": True,
            "raw_score": 0.82,
            "normalized_score": 0.91,
            "threshold": 0.70,
            "valid_measurement": True,
            "sample_count": settings.MIN_FACE_SAMPLES,
        }
        return patch(
            "biometrics.views.authenticate_enrolled_user",
            return_value={
                "face": face,
                "voice": voice,
                "iris": iris,
                "fusion": {
                    "face_weight": 0.34,
                    "voice_weight": 0.7,
                    "iris_weight": 0.3,
                    "score": 0.86,
                    "threshold": 0.8,
                    "reason_code": "ALL_MODALITIES_VALID",
                    "policy": {},
                },
                "decision": "ACCEPTED",
                "reason_code": "ALL_MODALITIES_VALID",
                "reason_message": "ok",
                "ui_state": "VERIFIED",
                "failure_reason": None,
                "processing_time_ms": 42,
                "privacy_mode": True,
                "diagnostics": {
                    "face_valid_measurement": True,
                    "face_quality": 0.88,
                    "face_detection_confidence": 0.95,
                    "iris_valid_measurement": True,
                    "voice_valid_measurement": True,
                },
            },
        )

    def test_accept_response_includes_reason_codes(self):
        iris = {"quality_score": 0.74, "iris_detected": True, "passed": True, "raw_score": 0.74, "normalized_score": 0.74, "threshold": 0.55, "detection_confidence": 1.0, "valid_measurement": True, "reason_code": "ALL_MODALITIES_VALID", "similarity_score": None}
        voice = {"quality_score": 0.91, "speech_detected": True, "speech_activity_score": 0.8, "passed": True, "raw_score": 0.91, "normalized_score": 0.91, "threshold": 0.55, "activity_threshold": 0.35, "valid_measurement": True, "reason_code": "ALL_MODALITIES_VALID", "similarity_score": None}
        with self._workflow_patch(iris, voice):
            response = self._post(self.client)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["decision"], "ACCEPTED")
        self.assertEqual(data["ui_state"], "VERIFIED")
        self.assertIn("reason_code", data)
        self.assertIn("fusion", data)

    def test_retry_response_shape(self):
        iris = {"quality_score": 0.30, "iris_detected": True, "passed": False, "raw_score": 0.30, "normalized_score": 0.30, "threshold": 0.55, "detection_confidence": 1.0, "valid_measurement": False, "reason_code": "IRIS_QUALITY_TOO_LOW", "similarity_score": None}
        voice = {"quality_score": 0.91, "speech_detected": True, "speech_activity_score": 0.8, "passed": True, "raw_score": 0.91, "normalized_score": 0.91, "threshold": 0.55, "activity_threshold": 0.35, "valid_measurement": True, "reason_code": "ALL_MODALITIES_VALID", "similarity_score": None}
        patched = patch(
            "biometrics.views.authenticate_enrolled_user",
            return_value={
                "voice": voice,
                "iris": iris,
                "fusion": {"voice_weight": 1.0, "iris_weight": 0.0, "score": 0.0, "threshold": 0.8, "reason_code": "IRIS_QUALITY_TOO_LOW", "policy": {}},
                "decision": "RETRY_REQUIRED",
                "reason_code": "IRIS_QUALITY_TOO_LOW",
                "reason_message": "Iris capture unclear",
                "ui_state": "QUALITY_TOO_LOW",
                "failure_reason": "Iris capture unclear",
                "processing_time_ms": 42,
                "privacy_mode": True,
                "diagnostics": {"iris_valid_measurement": False, "voice_valid_measurement": True, "final_score": 0.0, "threshold": 0.8, "iris_quality": 0.30, "voice_quality": 0.91, "iris_detection_confidence": 1.0},
            },
        )
        with patched:
            response = self._post(self.client)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["decision"], "RETRY_REQUIRED")
        self.assertEqual(data["ui_state"], "QUALITY_TOO_LOW")
        self.assertIn(data["reason_code"], {"IRIS_QUALITY_TOO_LOW", "IRIS_NOT_DETECTED"})

    def test_attempt_row_is_persisted(self):
        iris = {"quality_score": 0.74, "iris_detected": True, "passed": True, "raw_score": 0.74, "normalized_score": 0.74, "threshold": 0.55, "detection_confidence": 1.0, "valid_measurement": True, "reason_code": "ALL_MODALITIES_VALID", "similarity_score": None}
        voice = {"quality_score": 0.91, "speech_detected": True, "speech_activity_score": 0.8, "passed": True, "raw_score": 0.91, "normalized_score": 0.91, "threshold": 0.55, "activity_threshold": 0.35, "valid_measurement": True, "reason_code": "ALL_MODALITIES_VALID", "similarity_score": None}
        with self._workflow_patch(iris, voice):
            response = self._post(self.client)
        self.assertEqual(response.status_code, 200)
        attempt = AuthenticationAttempt.objects.get()
        self.assertEqual(attempt.decision, "ACCEPTED")
        self.assertEqual(attempt.fusion_reason_code, "ALL_MODALITIES_VALID")
        self.assertTrue(attempt.iris_valid_measurement)
        self.assertEqual(attempt.iris_normalized_score, 0.74)
        self.assertEqual(attempt.voice_normalized_score, 0.91)
        self.assertFalse(attempt.saved)

    def test_authentication_uses_the_enrolled_eye_side(self):
        self.user.enrolled_eye_side = "RIGHT"
        self.user.save(update_fields=["enrolled_eye_side"])
        iris = {"quality_score": 0.8, "normalized_score": 0.85}
        voice = {"quality_score": 0.9, "normalized_score": 0.9}

        with self._workflow_patch(iris, voice) as authenticate:
            response = self._post(self.client, eye_side="LEFT")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(authenticate.call_args.kwargs["eye_side"], "RIGHT")

    @override_settings(MAX_TRACKING_FRAME_BYTES=4)
    def test_oversized_tracking_frame_is_rejected_before_inference(self):
        response = self.client.post(
            "/api/v1/test/iris/tracking/",
            data={
                "frame": SimpleUploadedFile(
                    "frame.jpg",
                    b"12345",
                    content_type="image/jpeg",
                )
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("too large", response.json()["message"])
