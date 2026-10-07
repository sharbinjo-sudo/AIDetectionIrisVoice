import 'dart:async';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:permission_handler/permission_handler.dart';

import '../../../../core/camera/camera_frame_encoder.dart';
import '../../../../core/io/local_file_cleanup.dart';
import '../../../../core/networking/dio_client.dart';
import '../../../../shared/widgets/camera_preview_card.dart';
import '../../../../shared/widgets/permission_request_card.dart';
import '../../data/iris_tracking_repository.dart';
import '../../models/iris_tracking_filter.dart';
import '../../models/iris_tracking_result.dart';

enum _LiveTrackingState {
  starting,
  searching,
  uncertain,
  locked,
  // The backend was reached but the frame could not be processed (HTTP 4xx):
  // the backend's reason is shown instead of blaming connectivity.
  processingFailure,
  // Network failure / connection refused / 5xx: the backend is unusable.
  unavailable,
}

class LiveCameraPanel extends ConsumerStatefulWidget {
  const LiveCameraPanel({
    super.key,
    required this.instructions,
    required this.onCaptured,
    required this.onRetake,
    this.capturedPath,
    this.captureButtonLabel = 'Capture',
    this.requiredStableFrames = 3,
    this.onStableFrameProgress,
    this.requiredEyeSide,
    this.showAlignmentDebug = false,
  });

  final List<String> instructions;
  final ValueChanged<String> onCaptured;
  final VoidCallback onRetake;

  final String? capturedPath;
  final String captureButtonLabel;

  /// Consecutive stable iris frames used for alignment guidance only.
  final int requiredStableFrames;

  /// Reports [current, required] consecutive stable iris frames so hosts can
  /// show capture-readiness progress.
  final void Function(int current, int required)? onStableFrameProgress;
  final String? requiredEyeSide;

  /// Runtime alignment diagnostics for the Test page. The compile-time flag
  /// remains available, but callers no longer need a special build to inspect
  /// Face Landmarker eye ROIs and Worldcoin mask contours.
  final bool showAlignmentDebug;

  @override
  ConsumerState<LiveCameraPanel> createState() => _LiveCameraPanelState();
}

class _LiveCameraPanelState extends ConsumerState<LiveCameraPanel>
    with WidgetsBindingObserver {
  // camera_web does not expose startImageStream. Its takePicture method copies
  // the current HTML video frame to a canvas, so polling here still analyses
  // the live video rather than waiting for a user-taken photograph.
  // Web's camera plugin exposes the current video frame through takePicture.
  // Poll quickly so the next request starts on the first timer tick after the
  // previous response; _trackingRequestGeneration still permits only one
  // capture/inference request at a time.
  static const _fallbackTrackingInterval = Duration(milliseconds: 33);
  static const _debugTracking = bool.fromEnvironment('IRIS_TRACKING_DEBUG');

  CameraController? _controller;
  List<CameraDescription> _cameras = const [];
  int _currentCameraIndex = 0;
  bool _permissionDenied = false;
  bool _isInitializing = true;
  bool _isCapturing = false;
  int? _trackingRequestGeneration;
  int _trackingGeneration = 0;
  Timer? _fallbackTrackingTimer;
  List<IrisTrackingResult> _tracking = const [];
  List<Rect> _eyeRois = const [];
  Size? _trackingSourceSize;
  final Map<String, IrisTrackingFilter> _trackingFilters = {};
  bool _trackingCoordinatesMirrored = false;
  int _consecutiveStableIrisFrames = 0;
  int _lastReportedStableFrames = -1;
  _LiveTrackingState _trackingState = _LiveTrackingState.starting;
  String? _trackingFailure;
  String? _cameraError;
  bool _lifecycleSuspended = false;
  bool _permissionPermanentlyDenied = false;

  IrisTrackingRepository get _trackingRepository =>
      IrisTrackingRepository(ref.read(dioProvider));

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _setup();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.resumed:
        if (_lifecycleSuspended) {
          _lifecycleSuspended = false;
          unawaited(_resumeCamera());
        }
      case AppLifecycleState.inactive:
      case AppLifecycleState.paused:
      case AppLifecycleState.hidden:
      case AppLifecycleState.detached:
        if (!_lifecycleSuspended) {
          _lifecycleSuspended = true;
          unawaited(_suspendCamera());
        }
    }
  }

  Future<void> _setup() async {
    final status = await Permission.camera.request();
    if (!status.isGranted) {
      if (!mounted) return;
      setState(() {
        _permissionDenied = true;
        // Browsers report a denied site permission as permanently denied, but
        // there is no native app-settings screen to open from Flutter web.
        // Keep the in-app retry available so the user can allow the camera in
        // the browser's site controls and try again.
        _permissionPermanentlyDenied = !kIsWeb && status.isPermanentlyDenied;
        _isInitializing = false;
      });
      return;
    }
    try {
      _cameras = await availableCameras();
      if (_cameras.isEmpty) {
        setState(() {
          _cameraError = 'No camera device was found on this device.';
          _isInitializing = false;
        });
        return;
      }
      final frontIndex = _cameras.indexWhere(
        (camera) => camera.lensDirection == CameraLensDirection.front,
      );
      _currentCameraIndex = frontIndex >= 0 ? frontIndex : 0;
      await _initController();
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _cameraError = _friendlyCameraError(error);
        _isInitializing = false;
      });
    }
  }

  Future<void> _initController() async {
    await _stopTracking();
    await _controller?.dispose();
    final controller = CameraController(
      _cameras[_currentCameraIndex],
      ResolutionPreset.high,
      enableAudio: false,
      imageFormatGroup: _imageFormatForPlatform(),
    );
    await controller.initialize();
    if (!mounted || _lifecycleSuspended) {
      await controller.dispose();
      return;
    }
    setState(() {
      _controller = controller;
      _isInitializing = false;
      _permissionDenied = false;
      _permissionPermanentlyDenied = false;
      _cameraError = null;
    });
    if (widget.capturedPath == null) {
      await _startTracking(controller);
    }
  }

  Future<void> _suspendCamera() async {
    await _stopTracking();
    final controller = _controller;
    _controller = null;
    if (controller != null) {
      try {
        await controller.dispose();
      } catch (_) {
        // The operating system may already have reclaimed the camera.
      }
    }
  }

  Future<void> _resumeCamera() async {
    if (!mounted) return;
    setState(() {
      _isInitializing = true;
      _cameraError = null;
    });
    try {
      if (_cameras.isEmpty) {
        await _setup();
      } else {
        await _initController();
      }
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _isInitializing = false;
        _cameraError = _friendlyCameraError(error);
      });
    }
  }

  String _friendlyCameraError(Object error) {
    if (error is CameraException) {
      final description =
          error.description ??
          'The camera could not be started (${error.code}).';
      if (kIsWeb) {
        return '$description Allow camera access in the browser site controls. '
            'Camera capture requires HTTPS or localhost.';
      }
      return description;
    }
    return 'The camera could not be started. Close other apps using it and try again. Detail: $error';
  }

  ImageFormatGroup _imageFormatForPlatform() {
    if (kIsWeb) {
      return ImageFormatGroup.unknown;
    }
    return switch (defaultTargetPlatform) {
      TargetPlatform.android => ImageFormatGroup.yuv420,
      TargetPlatform.iOS => ImageFormatGroup.bgra8888,
      _ => ImageFormatGroup.unknown,
    };
  }

  Future<void> _startTracking(CameraController controller) async {
    final generation = ++_trackingGeneration;
    if (mounted) {
      setState(() {
        _trackingState = _LiveTrackingState.searching;
        _trackingFailure = null;
      });
    }
    if (controller.supportsImageStreaming()) {
      try {
        await controller.startImageStream((frame) {
          unawaited(_trackStreamFrame(frame, controller, generation));
        });
        return;
      } catch (_) {
        // Platforms without a working image stream use periodic camera frames.
      }
    }
    _fallbackTrackingTimer?.cancel();
    _fallbackTrackingTimer = Timer.periodic(_fallbackTrackingInterval, (_) {
      unawaited(_trackCapturedFrame(controller, generation));
    });
    unawaited(_trackCapturedFrame(controller, generation));
  }

  Future<void> _trackStreamFrame(
    CameraImage frame,
    CameraController controller,
    int generation,
  ) async {
    if (!_canTrack(controller, generation)) {
      return;
    }
    _trackingRequestGeneration = generation;
    try {
      final bytes = await encodeCameraFrame(
        frame,
        rotationDegrees: cameraFrameRotation(
          controller.description,
          controller.value.deviceOrientation,
        ),
      );
      if (bytes == null || !_canApplyTracking(controller, generation)) {
        if (bytes == null) {
          _showTrackingFailure(
            StateError('The live camera frame format could not be encoded.'),
            generation,
          );
        }
        return;
      }
      final result = await _trackingRepository.track(bytes);
      _applyTracking(result, generation, coordinatesMirrored: false);
    } catch (error) {
      _showTrackingFailure(error, generation);
    } finally {
      if (_trackingRequestGeneration == generation) {
        _trackingRequestGeneration = null;
      }
    }
  }

  Future<void> _trackCapturedFrame(
    CameraController controller,
    int generation,
  ) async {
    if (!_canTrack(controller, generation) ||
        controller.value.isTakingPicture) {
      return;
    }
    _trackingRequestGeneration = generation;
    XFile? frame;
    try {
      frame = await controller.takePicture();
      final bytes = await frame.readAsBytes();
      if (!_canApplyTracking(controller, generation)) {
        return;
      }
      final result = await _trackingRepository.track(bytes);
      _applyTracking(
        result,
        generation,
        coordinatesMirrored:
            kIsWeb &&
            controller.description.lensDirection == CameraLensDirection.front,
      );
    } catch (error) {
      _showTrackingFailure(error, generation);
    } finally {
      if (frame != null) {
        await deleteLocalFileIfExists(frame.path);
      }
      if (_trackingRequestGeneration == generation) {
        _trackingRequestGeneration = null;
      }
    }
  }

  bool _canTrack(CameraController controller, int generation) {
    return mounted &&
        generation == _trackingGeneration &&
        identical(_controller, controller) &&
        widget.capturedPath == null &&
        !_isCapturing &&
        _trackingRequestGeneration != generation &&
        controller.value.isInitialized;
  }

  bool _canApplyTracking(CameraController controller, int generation) {
    return mounted &&
        generation == _trackingGeneration &&
        identical(_controller, controller) &&
        widget.capturedPath == null;
  }

  void _applyTracking(
    IrisTrackingFrame frame,
    int generation, {
    required bool coordinatesMirrored,
  }) {
    if (!mounted || generation != _trackingGeneration) {
      return;
    }
    final timestamp = _timestampSeconds();
    if (!frame.detected) {
      _consecutiveStableIrisFrames = 0;
      for (final filter in _trackingFilters.values) {
        filter.markLost(timestamp);
      }
      setState(() {
        _tracking = const [];
        _eyeRois = frame.eyeRois;
        _trackingSourceSize = frame.sourceSize;
        _trackingCoordinatesMirrored = coordinatesMirrored;
        _trackingState = _LiveTrackingState.searching;
        _trackingFailure = null;
      });
      _reportStableFrameProgress();
      return;
    }

    final detectedSides = frame.eyes.map((eye) => eye.eyeSide).toSet();
    for (final entry in _trackingFilters.entries) {
      if (!detectedSides.contains(entry.key)) {
        entry.value.markLost(timestamp);
      }
    }
    final filtered = frame.eyes
        .map(
          (eye) => _trackingFilters
              .putIfAbsent(eye.eyeSide, IrisTrackingFilter.new)
              .filter(eye, timestamp),
        )
        .whereType<IrisTrackingResult>()
        .toList(growable: false);
    _consecutiveStableIrisFrames =
        filtered.any(
          (eye) =>
              eye.stable &&
              (widget.requiredEyeSide == null ||
                  eye.eyeSide == widget.requiredEyeSide),
        )
        ? _consecutiveStableIrisFrames + 1
        : 0;
    _reportStableFrameProgress();
    setState(() {
      _trackingCoordinatesMirrored = coordinatesMirrored;
      _tracking = filtered;
      _eyeRois = frame.eyeRois;
      _trackingSourceSize = frame.sourceSize;
      _trackingState = filtered.isEmpty
          ? _LiveTrackingState.searching
          : filtered.every((eye) => eye.stable)
          ? _LiveTrackingState.locked
          : _LiveTrackingState.uncertain;
      _trackingFailure = null;
    });
  }

  void _reportStableFrameProgress() {
    if (widget.onStableFrameProgress == null) {
      return;
    }
    if (_lastReportedStableFrames == _consecutiveStableIrisFrames) {
      return;
    }
    _lastReportedStableFrames = _consecutiveStableIrisFrames;
    widget.onStableFrameProgress!(
      _consecutiveStableIrisFrames,
      widget.requiredStableFrames,
    );
  }

  void _showTrackingFailure(Object error, int generation) {
    if (!mounted || generation != _trackingGeneration) {
      return;
    }
    final failure = error is IrisTrackingFailedException
        ? error
        : null;
    final isProcessingFailure = failure != null;
    final detail = failure?.reason;
    final message = failure?.message ?? error.toString();
    for (final filter in _trackingFilters.values) {
      filter.markLost(_timestampSeconds());
    }
    setState(() {
      _tracking = const [];
      _eyeRois = const [];
      _trackingSourceSize = null;
      _trackingState = isProcessingFailure
          ? _LiveTrackingState.processingFailure
          : _LiveTrackingState.unavailable;
      _trackingFailure = detail == null ? message : '$message ($detail)';
    });
  }

  double _timestampSeconds() {
    return DateTime.now().microsecondsSinceEpoch /
        Duration.microsecondsPerSecond;
  }

  Future<void> _stopTracking() async {
    _trackingGeneration += 1;
    _fallbackTrackingTimer?.cancel();
    _fallbackTrackingTimer = null;
    _tracking = const [];
    _eyeRois = const [];
    _trackingSourceSize = null;
    _consecutiveStableIrisFrames = 0;
    _reportStableFrameProgress();
    for (final filter in _trackingFilters.values) {
      filter.reset();
    }
    _trackingFilters.clear();
    _trackingState = _LiveTrackingState.starting;
    _trackingFailure = null;
    final controller = _controller;
    if (controller != null &&
        controller.value.isInitialized &&
        controller.value.isStreamingImages) {
      try {
        await controller.stopImageStream();
      } catch (_) {
        // Disposal still releases the camera when a platform stops abruptly.
      }
    }
  }

  Future<void> _capture() async {
    final controller = _controller;
    if (controller == null || _isCapturing || !controller.value.isInitialized) {
      return;
    }
    setState(() {
      _isCapturing = true;
    });
    try {
      await _stopTracking();
      if (!mounted || _lifecycleSuspended || _controller != controller) return;
      for (
        var attempt = 0;
        controller.value.isTakingPicture && attempt < 30;
        attempt += 1
      ) {
        await Future<void>.delayed(const Duration(milliseconds: 16));
      }
      if (!mounted || _lifecycleSuspended || _controller != controller) return;
      final file = await controller.takePicture();
      if (!mounted || _lifecycleSuspended || _controller != controller) {
        await deleteLocalFileIfExists(file.path);
        return;
      }
      widget.onCaptured(file.path);
      // Capture-only flows (including the face-primary prototype enrollment)
      // keep the camera mounted for the next sample. The normal flow sets
      // capturedPath, so it intentionally remains paused until Retake.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        final controller = _controller;
        if (mounted &&
            widget.capturedPath == null &&
            !_lifecycleSuspended &&
            controller != null &&
            controller.value.isInitialized) {
          unawaited(_startTracking(controller));
        }
      });
    } catch (error) {
      if (mounted) {
        setState(() => _cameraError = _friendlyCameraError(error));
        final controller = _controller;
        if (controller != null && !_lifecycleSuspended) {
          await _startTracking(controller);
        }
      }
    } finally {
      if (mounted) {
        setState(() => _isCapturing = false);
      }
    }
  }

  void _requestCapture() {
    if (_controller == null ||
        !_controller!.value.isInitialized ||
        _isCapturing ||
        widget.capturedPath != null) {
      return;
    }
    // Tracking is guidance only. Take one photo per explicit button press;
    // backend quality validation still decides whether it is usable.
    unawaited(_capture());
  }

  Future<void> _switchCamera() async {
    if (_cameras.length < 2) {
      return;
    }
    setState(() {
      _isInitializing = true;
    });
    await _stopTracking();
    _currentCameraIndex = (_currentCameraIndex + 1) % _cameras.length;
    await _initController();
  }

  @override
  void didUpdateWidget(covariant LiveCameraPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.requiredEyeSide != widget.requiredEyeSide) {
      _consecutiveStableIrisFrames = 0;
      _reportStableFrameProgress();
    }
    if (oldWidget.capturedPath == widget.capturedPath) {
      return;
    }
    if (widget.capturedPath != null) {
      unawaited(_stopTracking());
    } else if (_controller case final controller?) {
      unawaited(_startTracking(controller));
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _trackingGeneration += 1;
    _fallbackTrackingTimer?.cancel();
    final controller = _controller;
    if (controller != null) {
      if (controller.value.isStreamingImages) {
        unawaited(
          controller.stopImageStream().then((_) => controller.dispose()),
        );
      } else {
        unawaited(controller.dispose());
      }
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final alignmentDebug = widget.showAlignmentDebug || _debugTracking;
    if (_permissionDenied) {
      return PermissionRequestCard(
        title: 'Camera access required',
        message:
            'Camera access is required to capture the eye challenge image.',
        onRequest: _permissionPermanentlyDenied
            ? () async {
                await openAppSettings();
              }
            : _setup,
        actionLabel: _permissionPermanentlyDenied
            ? 'Open app settings'
            : 'Grant access',
      );
    }

    if (_cameraError != null) {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Text(_cameraError!),
        ),
      );
    }

    if (_isInitializing) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(18),
          child: Center(child: CircularProgressIndicator()),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        CameraPreviewCard(
          controller: widget.capturedPath == null ? _controller : null,
          capturedPath: widget.capturedPath,
          instructions: widget.instructions,
          tracking: _tracking,
          eyeRois: _eyeRois,
          trackingSourceSize: _trackingSourceSize,
          mirrorHorizontally:
              _cameras[_currentCameraIndex].lensDirection ==
                  CameraLensDirection.front &&
              !_trackingCoordinatesMirrored,
          debugTracking: alignmentDebug,
        ),
        const SizedBox(height: 8),
        _TrackingStatus(
          state: _trackingState,
          trackedEyeCount: _tracking.length,
          debugDetail: alignmentDebug ? _trackingFailure : null,
          failureDetail: _trackingFailure,
        ),
        const SizedBox(height: 4),
        LinearProgressIndicator(
          value: _consecutiveStableIrisFrames / widget.requiredStableFrames,
          minHeight: 4,
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            FilledButton(
              onPressed: widget.capturedPath == null && !_isCapturing
                  ? _requestCapture
                  : null,
              child: _isCapturing
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Text(widget.captureButtonLabel),
            ),
            OutlinedButton(
              onPressed: widget.capturedPath != null ? widget.onRetake : null,
              child: const Text('Retake'),
            ),
            OutlinedButton(
              onPressed: _switchCamera,
              child: const Text('Switch Camera'),
            ),
          ],
        ),
      ],
    );
  }
}

class _TrackingStatus extends StatelessWidget {
  const _TrackingStatus({
    required this.state,
    required this.trackedEyeCount,
    this.debugDetail,
    this.failureDetail,
  });

  final _LiveTrackingState state;
  final int trackedEyeCount;
  final String? debugDetail;
  final String? failureDetail;

  @override
  Widget build(BuildContext context) {
    // The backend's processing-failure reason is always shown for 4xx states;
    // other states only show extra detail when alignment debug is enabled.
    final effectiveDetail = state == _LiveTrackingState.processingFailure
        ? (failureDetail ?? debugDetail)
        : debugDetail;
    final (icon, message, color) = switch (state) {
      _LiveTrackingState.starting => (
        Icons.sync,
        'Starting live iris tracking…',
        Theme.of(context).colorScheme.onSurfaceVariant,
      ),
      _LiveTrackingState.searching => (
        Icons.visibility_outlined,
        'Live tracking: keep your full head visible and both irises open.',
        Theme.of(context).colorScheme.onSurfaceVariant,
      ),
      _LiveTrackingState.uncertain => (
        Icons.adjust,
        'Iris found, but the fit is uncertain. Hold steady.',
        Colors.orange,
      ),
      _LiveTrackingState.locked => (
        Icons.check_circle_outline,
        '$trackedEyeCount ${trackedEyeCount == 1 ? 'iris' : 'irises'} locked — tracking live video.',
        Colors.green,
      ),
      _LiveTrackingState.processingFailure => (
        Icons.visibility_off_outlined,
        'The eye/frame could not be processed for tracking.',
        Theme.of(context).colorScheme.error,
      ),
      _LiveTrackingState.unavailable => (
        Icons.error_outline,
        'Live iris tracking is unavailable. Check that the backend is running.',
        Theme.of(context).colorScheme.error,
      ),
    };
    return Semantics(
      liveRegion: true,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 18, color: color),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              effectiveDetail == null
                  ? message
                  : '$message\n$effectiveDetail',
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: color),
            ),
          ),
        ],
      ),
    );
  }
}
