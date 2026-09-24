import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../features/test_mode/models/iris_tracking_result.dart';
import 'iris_tracking_overlay.dart';

class CameraPreviewCard extends StatelessWidget {
  const CameraPreviewCard({
    super.key,
    this.controller,
    this.capturedPath,
    this.instructions = const [],
    this.tracking = const [],
    this.eyeRois = const [],
    this.trackingSourceSize,
    this.mirrorHorizontally = false,
    this.debugTracking = false,
  });

  static const _previewFit = BoxFit.cover;

  final CameraController? controller;
  final String? capturedPath;
  final List<String> instructions;
  final List<IrisTrackingResult> tracking;
  final List<Rect> eyeRois;
  final Size? trackingSourceSize;
  final bool mirrorHorizontally;
  final bool debugTracking;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final item in instructions)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Text('- $item'),
              ),
            const SizedBox(height: 12),
            if (capturedPath != null)
              AspectRatio(
                aspectRatio: 1.2,
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(18),
                  child: kIsWeb
                      ? Image.network(capturedPath!, fit: _previewFit)
                      : Image.file(File(capturedPath!), fit: _previewFit),
                ),
              )
            else if (controller case final camera?)
              ValueListenableBuilder<CameraValue>(
                valueListenable: camera,
                builder: (context, value, _) {
                  if (!value.isInitialized) {
                    return const AspectRatio(
                      aspectRatio: 1.2,
                      child: ColoredBox(color: Colors.black12),
                    );
                  }
                  final sourceSize = trackingSourceSize?.isEmpty == false
                      ? trackingSourceSize!
                      : tracking.isNotEmpty &&
                            !tracking.first.sourceSize.isEmpty
                      ? tracking.first.sourceSize
                      : _orientedPreviewSize(value);
                  return AspectRatio(
                    aspectRatio: sourceSize.aspectRatio,
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(18),
                      child: Stack(
                        fit: StackFit.expand,
                        children: [
                          FittedBox(
                            fit: _previewFit,
                            alignment: Alignment.center,
                            clipBehavior: Clip.hardEdge,
                            child: SizedBox.fromSize(
                              size: sourceSize,
                              child: CameraPreview(camera),
                            ),
                          ),
                          IrisTrackingOverlay(
                            tracking: tracking,
                            eyeRois: eyeRois,
                            sourceSize: sourceSize,
                            fit: _previewFit,
                            mirrorHorizontally: mirrorHorizontally,
                            showTracker: true,
                            debugMode: debugTracking,
                          ),
                        ],
                      ),
                    ),
                  );
                },
              )
            else
              const AspectRatio(
                aspectRatio: 1.2,
                child: ColoredBox(color: Colors.black12),
              ),
          ],
        ),
      ),
    );
  }

  Size _orientedPreviewSize(CameraValue value) {
    final raw = value.previewSize ?? const Size(4, 3);
    final landscape = const {
      DeviceOrientation.landscapeLeft,
      DeviceOrientation.landscapeRight,
    }.contains(value.deviceOrientation);
    return landscape ? raw : Size(raw.height, raw.width);
  }
}
