import 'dart:async';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';

import '../../../../shared/widgets/permission_request_card.dart';

class FaceCapturePanel extends StatefulWidget {
  const FaceCapturePanel({
    super.key,
    required this.samplePaths,
    required this.requiredSamples,
    required this.onCaptured,
    required this.onRetake,
  });

  final List<String> samplePaths;
  final int requiredSamples;
  final ValueChanged<String> onCaptured;
  final VoidCallback onRetake;

  @override
  State<FaceCapturePanel> createState() => _FaceCapturePanelState();
}

class _FaceCapturePanelState extends State<FaceCapturePanel>
    with WidgetsBindingObserver {
  CameraController? _controller;
  bool _initializing = true;
  bool _capturing = false;
  bool _permissionDenied = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_initialize());
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _controller == null) {
      unawaited(_initialize());
    } else if (state != AppLifecycleState.resumed) {
      final controller = _controller;
      _controller = null;
      unawaited(controller?.dispose());
    }
  }

  Future<void> _initialize() async {
    if (mounted) {
      setState(() {
        _initializing = true;
        _error = null;
      });
    }
    final permission = await Permission.camera.request();
    if (!permission.isGranted) {
      if (!mounted) return;
      setState(() {
        _permissionDenied = true;
        _initializing = false;
      });
      return;
    }
    try {
      final cameras = await availableCameras();
      if (cameras.isEmpty) throw StateError('No camera was found.');
      final camera = cameras.firstWhere(
        (item) => item.lensDirection == CameraLensDirection.front,
        orElse: () => cameras.first,
      );
      final controller = CameraController(
        camera,
        ResolutionPreset.high,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.unknown,
      );
      await controller.initialize();
      if (!mounted) {
        await controller.dispose();
        return;
      }
      await _controller?.dispose();
      setState(() {
        _controller = controller;
        _permissionDenied = false;
        _initializing = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = kIsWeb
            ? 'The iris camera could not start. Allow camera access in the browser site controls and use HTTPS or localhost. Detail: $error'
            : 'The iris camera could not start. Detail: $error';
        _initializing = false;
      });
    }
  }

  Future<void> _capture() async {
    final controller = _controller;
    if (controller == null ||
        !controller.value.isInitialized ||
        _capturing ||
        widget.samplePaths.length >= widget.requiredSamples) {
      return;
    }
    setState(() => _capturing = true);
    try {
      final file = await controller.takePicture();
      widget.onCaptured(file.path);
    } catch (error) {
      if (mounted) setState(() => _error = 'Iris capture failed: $error');
    } finally {
      if (mounted) setState(() => _capturing = false);
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    unawaited(_controller?.dispose());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_permissionDenied) {
      return PermissionRequestCard(
        title: 'Camera access required',
        message: 'Allow camera access, then capture several live iris samples.',
        onRequest: _initialize,
        actionLabel: 'Try again',
      );
    }
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Iris samples ${widget.samplePaths.length}/${widget.requiredSamples}',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 6),
            const Text(
              'Keep one eye and the surrounding iris area visible. Use even front lighting, look straight at the camera, and move slightly between captures.',
            ),
            const SizedBox(height: 12),
            AspectRatio(
              aspectRatio: 4 / 3,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(16),
                child: _initializing
                    ? const ColoredBox(
                        color: Colors.black12,
                        child: Center(child: CircularProgressIndicator()),
                      )
                    : _controller == null
                    ? const ColoredBox(color: Colors.black12)
                    : CameraPreview(_controller!),
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 10),
              Text(_error!, style: const TextStyle(color: Colors.red)),
            ],
            const SizedBox(height: 12),
            Wrap(
              spacing: 12,
              runSpacing: 10,
              children: [
                FilledButton.icon(
                  onPressed:
                      _capturing ||
                          _controller == null ||
                          widget.samplePaths.length >= widget.requiredSamples
                      ? null
                      : _capture,
                  icon: const Icon(Icons.visibility_rounded),
                  label: Text(
                    _capturing
                        ? 'Capturing...'
                        : widget.samplePaths.length >= widget.requiredSamples
                        ? 'Iris samples ready'
                        : 'Capture iris sample',
                  ),
                ),
                if (widget.samplePaths.isNotEmpty)
                  OutlinedButton.icon(
                    onPressed: widget.onRetake,
                    icon: const Icon(Icons.refresh_rounded),
                    label: const Text('Retake all'),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
