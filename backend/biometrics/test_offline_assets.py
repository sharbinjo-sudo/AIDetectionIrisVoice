from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .services.exceptions import ModelUnavailableError
from .services.model_assets import ensure_remote_asset


@override_settings(BIOMETRIC_OFFLINE_MODE=True)
class OfflineAssetsTests(SimpleTestCase):
    @patch("speechbrain.inference.speaker.EncoderClassifier.from_hparams")
    def test_voice_loader_disables_remote_fetches(self, from_hparams):
        from .services.engines import VoiceBiometricEngine

        with TemporaryDirectory() as directory:
            (Path(directory) / "hyperparams.yaml").touch()
            with override_settings(
                LOCAL_VOICE_MODEL_DIR=directory, VOICE_MODEL_CACHE_DIR=directory
            ):
                engine = VoiceBiometricEngine()
        self.assertTrue(engine.ready)
        from_hparams.assert_called_once()
        config = from_hparams.call_args.kwargs["fetch_config"]
        self.assertFalse(config.allow_network)
        self.assertFalse(config.allow_updates)

    @patch("biometrics.services.model_assets.urlopen")
    def test_missing_asset_fails_without_network(self, urlopen):
        with TemporaryDirectory() as directory:
            with self.assertRaisesMessage(ModelUnavailableError, "no download was attempted"):
                ensure_remote_asset(
                    destination=Path(directory) / "missing.onnx",
                    description="test model",
                    urls=["https://example.invalid/model.onnx"],
                )
        urlopen.assert_not_called()

    @patch("biometrics.services.model_assets.urlopen")
    def test_existing_asset_is_used_without_network(self, urlopen):
        with TemporaryDirectory() as directory:
            asset = Path(directory) / "model.onnx"
            asset.touch()
            self.assertEqual(
                ensure_remote_asset(destination=asset, description="test model", urls=[]),
                asset,
            )
        urlopen.assert_not_called()
