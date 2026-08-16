import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';

import '../../../../core/constants/app_constants.dart';
import '../../../../core/constants/verification_constants.dart';
import '../../../../shared/widgets/permission_request_card.dart';
import '../../../../shared/widgets/voice_waveform.dart';

class VoiceRecorderPanel extends StatefulWidget {
  const VoiceRecorderPanel({
    super.key,
    required this.onRecorded,
    required this.onRetake,
    this.recordedPath,
    this.title = 'Voice Challenge',
    this.phrase = AppConstants.verificationPhrase,
    this.autoStartRecording = false,
  });

  final void Function(String path, double durationSeconds) onRecorded;
  final VoidCallback onRetake;
  final String? recordedPath;
  final String title;
  final String phrase;
  final bool autoStartRecording;

  @override
  State<VoiceRecorderPanel> createState() => _VoiceRecorderPanelState();
}

class _VoiceRecorderPanelState extends State<VoiceRecorderPanel> {
  static const _sampleRate = 16000;
  static const _channels = 1;
  static const _speechLevelThreshold = 0.12;

  final _recorder = AudioRecorder();
  final _player = AudioPlayer();
  StreamSubscription<Amplitude>? _amplitudeSubscription;
  Timer? _recordingTimer;
  Timer? _countdownTimer;
  bool _permissionDenied = false;
  bool _recording = false;
  bool _autoStarted = false;
  int _elapsedSeconds = 0;
  int? _countdownValue;
  double _amplitude = 0.05;
  double _maxAmplitude = 0.0;
  bool _speechDetectedLocally = false;
  String? _currentRecordingPath;
  String? _runtimeError;

  @override
  void initState() {
    super.initState();
    if (widget.autoStartRecording) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _prepareAutoStart();
      });
    }
  }

  Future<void> _requestPermission() async {
    try {
      final granted = kIsWeb
          ? await _recorder.hasPermission()
          : (await Permission.microphone.request()).isGranted;
      if (!mounted) {
        return;
      }
      setState(() {
        _permissionDenied = !granted;
        _runtimeError = granted
            ? null
            : 'Microphone permission was denied. Allow microphone access and try again.';
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _permissionDenied = true;
        _runtimeError = 'Could not request microphone permission: $error';
      });
    }
  }

  Future<void> _prepareAutoStart() async {
    if (_autoStarted || widget.recordedPath != null || _recording) {
      return;
    }
    _autoStarted = true;
    await _requestPermission();
    if (!mounted || _permissionDenied) {
      return;
    }
    setState(
      () => _countdownValue = VerificationConstants.voiceCountdown.inSeconds,
    );
    _countdownTimer?.cancel();
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (timer) async {
      if (!mounted) {
        timer.cancel();
        return;
      }
      final current = _countdownValue ?? 0;
      if (current <= 1) {
        timer.cancel();
        setState(() => _countdownValue = null);
        await _startRecording(skipPermissionCheck: true);
        return;
      }
      setState(() => _countdownValue = current - 1);
    });
  }

  Future<RecordConfig> _buildRecordConfig() async {
    final wavSupported = await _recorder.isEncoderSupported(AudioEncoder.wav);
    if (!wavSupported) {
      throw StateError(
        'WAV recording is not supported on this browser/device. Use Chrome or Edge on localhost for the pretrained voice model.',
      );
    }

    return const RecordConfig(
      encoder: AudioEncoder.wav,
      numChannels: _channels,
      sampleRate: _sampleRate,
      autoGain: true,
      echoCancel: true,
      noiseSuppress: true,
    );
  }

  Future<String> _newRecordingPath() async {
    final filename = 'voice_${DateTime.now().millisecondsSinceEpoch}.wav';
    if (kIsWeb) {
      return filename;
    }
    final directory = await getTemporaryDirectory();
    return '${directory.path}/$filename';
  }

  double _normalizeDecibels(double decibels) {
    if (!decibels.isFinite) {
      return 0.0;
    }
    return ((decibels + 60.0) / 60.0).clamp(0.0, 1.0).toDouble();
  }

  String _friendlyRecorderError(Object error) {
    final detail = error.toString().replaceFirst('Bad state: ', '');
    return 'Could not start voice recording. Check microphone permission, close other apps using the mic, then try again. Detail: $detail';
  }

  Future<void> _startRecording({bool skipPermissionCheck = false}) async {
    if (_recording) {
      return;
    }
    try {
      final granted = skipPermissionCheck || await _recorder.hasPermission();
      if (!granted) {
        setState(() {
          _permissionDenied = true;
          _runtimeError =
              'Microphone permission is required for voice verification.';
        });
        return;
      }

      await _player.stop();
      final config = await _buildRecordConfig();
      final path = await _newRecordingPath();

      await _recorder.start(config, path: path);

      setState(() {
        _currentRecordingPath = path;
        _elapsedSeconds = 0;
        _amplitude = 0.05;
        _maxAmplitude = 0.0;
        _speechDetectedLocally = false;
        _runtimeError = null;
        _permissionDenied = false;
        _recording = true;
      });

      _amplitudeSubscription?.cancel();
      _amplitudeSubscription = _recorder
          .onAmplitudeChanged(const Duration(milliseconds: 140))
          .listen(
            (value) {
              if (!mounted) {
                return;
              }
              final normalizedAmplitude = _normalizeDecibels(value.current);
              setState(() {
                _amplitude = normalizedAmplitude;
                if (normalizedAmplitude > _maxAmplitude) {
                  _maxAmplitude = normalizedAmplitude;
                }
                if (normalizedAmplitude >= _speechLevelThreshold) {
                  _speechDetectedLocally = true;
                }
              });
            },
            onError: (Object error) {
              if (!mounted) {
                return;
              }
              setState(() {
                _runtimeError =
                    'Microphone level monitoring failed, but recording may still continue: $error';
              });
            },
          );
      _recordingTimer?.cancel();
      _recordingTimer = Timer.periodic(const Duration(seconds: 1), (
        timer,
      ) async {
        if (!mounted) {
          timer.cancel();
          return;
        }
        setState(() => _elapsedSeconds += 1);
        if (_elapsedSeconds >= VerificationConstants.maxVoiceSeconds) {
          await _stopRecording();
        }
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _recording = false;
        _countdownValue = null;
        _runtimeError = _friendlyRecorderError(error);
      });
    }
  }

  Future<void> _stopRecording() async {
    try {
      _recordingTimer?.cancel();
      _amplitudeSubscription?.cancel();
      final path = await _recorder.stop();
      if (!mounted) {
        return;
      }
      setState(() {
        _recording = false;
        _amplitude = 0.05;
      });
      if (path == null || path.isEmpty) {
        setState(() {
          _runtimeError =
              'No audio was captured. Allow microphone access and try again.';
        });
        return;
      }
      if (_elapsedSeconds < VerificationConstants.minVoiceSeconds) {
        setState(() {
          _currentRecordingPath = path;
          _runtimeError =
              'Recording is too short. Speak clearly for at least ${VerificationConstants.minVoiceSeconds} seconds and try again.';
        });
        return;
      }
      setState(() {
        _currentRecordingPath = path;
        _runtimeError = null;
      });
      widget.onRecorded(path, _elapsedSeconds.toDouble());
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _recording = false;
        _amplitude = 0.05;
        _runtimeError =
            'Could not stop or save the recording. Keep the tab active and try again. Detail: $error';
      });
    }
  }

  Future<void> _play() async {
    final path = widget.recordedPath ?? _currentRecordingPath;
    if (path == null) {
      return;
    }
    try {
      await _player.stop();
      await _player.play(kIsWeb ? UrlSource(path) : DeviceFileSource(path));
      if (mounted) {
        setState(() => _runtimeError = null);
      }
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _runtimeError =
            'The recording was captured but could not be played back in this browser. Detail: $error';
      });
    }
  }

  Future<void> _retake() async {
    await _player.stop();
    setState(() {
      _currentRecordingPath = null;
      _elapsedSeconds = 0;
      _amplitude = 0.05;
      _maxAmplitude = 0.0;
      _speechDetectedLocally = false;
      _countdownValue = null;
      _autoStarted = false;
      _runtimeError = null;
    });
    widget.onRetake();
    if (widget.autoStartRecording) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _prepareAutoStart();
      });
    }
  }

  @override
  void dispose() {
    _recordingTimer?.cancel();
    _countdownTimer?.cancel();
    _amplitudeSubscription?.cancel();
    _recorder.dispose();
    _player.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_permissionDenied) {
      return PermissionRequestCard(
        title: 'Microphone access required',
        message:
            _runtimeError ??
            'Microphone access is required for the spoken human challenge.',
        onRequest: _requestPermission,
      );
    }

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.title,
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 18),
            ),
            const SizedBox(height: 12),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(18),
                border: Border.all(
                  color: Theme.of(context).colorScheme.primary,
                ),
              ),
              child: Text(widget.phrase),
            ),
            const SizedBox(height: 16),
            if (_countdownValue != null) ...[
              Text('Starting in $_countdownValue...'),
              const SizedBox(height: 12),
            ],
            VoiceWaveform(amplitude: _amplitude, active: _recording),
            const SizedBox(height: 12),
            Text('Timer: $_elapsedSeconds s'),
            const SizedBox(height: 6),
            Text(
              'Local mic activity: ${_speechDetectedLocally ? 'Detected' : 'Not detected yet'}',
            ),
            Text('Max input level: ${_maxAmplitude.toStringAsFixed(2)}'),
            Text(
              'Tip: speak clearly for at least ${VerificationConstants.minVoiceSeconds} seconds. Chrome/Edge on localhost records WAV for the backend model.',
            ),
            if (_runtimeError != null) ...[
              const SizedBox(height: 10),
              Text(
                _runtimeError!,
                style: TextStyle(
                  color: Theme.of(context).colorScheme.error,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
            const SizedBox(height: 16),
            Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                FilledButton(
                  onPressed: _recording ? null : _startRecording,
                  child: const Text('Start Recording'),
                ),
                OutlinedButton(
                  onPressed: _recording ? _stopRecording : null,
                  child: const Text('Stop Recording'),
                ),
                OutlinedButton(
                  onPressed:
                      !_recording &&
                          (widget.recordedPath ?? _currentRecordingPath) != null
                      ? _play
                      : null,
                  child: const Text('Play Recording'),
                ),
                OutlinedButton(
                  onPressed:
                      !_recording &&
                          (widget.recordedPath ?? _currentRecordingPath) != null
                      ? _retake
                      : null,
                  child: const Text('Retake'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
