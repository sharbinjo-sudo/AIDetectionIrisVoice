import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';

import '../../../../shared/widgets/camera_preview_card.dart';
import '../../../../shared/widgets/permission_request_card.dart';

class LiveCameraPanel extends StatefulWidget {
  const LiveCameraPanel({
    super.key,
    required this.instructions,
    required this.onCaptured,
    required this.onRetake,
    this.capturedPath,
    this.captureButtonLabel = 'Capture',
  });

  final List<String> instructions;
  final ValueChanged<String> onCaptured;
  final VoidCallback onRetake;
  final String? capturedPath;
  final String captureButtonLabel;

  @override
  State<LiveCameraPanel> createState() => _LiveCameraPanelState();
}

class _LiveCameraPanelState extends State<LiveCameraPanel> {
  CameraController? _controller;
  List<CameraDescription> _cameras = const [];
  int _currentCameraIndex = 0;
  bool _permissionDenied = false;
  bool _isInitializing = true;
  bool _isCapturing = false;
  String? _cameraError;

  @override
  void initState() {
    super.initState();
    _setup();
  }

  Future<void> _setup() async {
    final status = await Permission.camera.request();
    if (!status.isGranted) {
      setState(() {
        _permissionDenied = true;
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
      setState(() {
        _cameraError = error.toString();
        _isInitializing = false;
      });
    }
  }

  Future<void> _initController() async {
    await _controller?.dispose();
    final controller = CameraController(
      _cameras[_currentCameraIndex],
      ResolutionPreset.high,
      enableAudio: false,
    );
    await controller.initialize();
    if (!mounted) {
      return;
    }
    setState(() {
      _controller = controller;
      _isInitializing = false;
      _permissionDenied = false;
      _cameraError = null;
    });
  }

  Future<void> _capture() async {
    if (_controller == null || _isCapturing || !_controller!.value.isInitialized) {
      return;
    }
    setState(() => _isCapturing = true);
    try {
      final file = await _controller!.takePicture();
      widget.onCaptured(file.path);
    } finally {
      if (mounted) {
        setState(() => _isCapturing = false);
      }
    }
  }

  Future<void> _switchCamera() async {
    if (_cameras.length < 2) {
      return;
    }
    setState(() => _isInitializing = true);
    _currentCameraIndex = (_currentCameraIndex + 1) % _cameras.length;
    await _initController();
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_permissionDenied) {
      return PermissionRequestCard(
        title: 'Camera access required',
        message: 'Camera access is required to capture the eye challenge image.',
        onRequest: _setup,
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
        ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            FilledButton(
              onPressed: widget.capturedPath == null ? _capture : null,
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
