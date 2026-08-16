import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'eye_guide_overlay.dart';

class CameraPreviewCard extends StatelessWidget {
  const CameraPreviewCard({
    super.key,
    this.controller,
    this.capturedPath,
    this.instructions = const [],
  });

  final CameraController? controller;
  final String? capturedPath;
  final List<String> instructions;

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
            AspectRatio(
              aspectRatio: controller?.value.aspectRatio ?? 1.2,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(18),
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    if (capturedPath != null)
                      kIsWeb
                          ? Image.network(capturedPath!, fit: BoxFit.cover)
                          : Image.file(File(capturedPath!), fit: BoxFit.cover)
                    else if (controller != null && controller!.value.isInitialized)
                      CameraPreview(controller!)
                    else
                      const ColoredBox(color: Colors.black12),
                    const EyeGuideOverlay(),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
