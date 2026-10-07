import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/features/test_mode/data/iris_tracking_repository.dart';

/// Replays canned responses/exceptions instead of performing real HTTP.
class _FakeAdapter implements HttpClientAdapter {
  _FakeAdapter(this._handler);

  final Object Function(RequestOptions options) _handler;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    final result = _handler(options);
    if (result is ResponseBody) {
      return result;
    }
    throw result;
  }

  @override
  void close({bool force = false}) {}
}

IrisTrackingRepository _repository(
  Object Function(RequestOptions options) handler,
) {
  final dio = Dio()..httpClientAdapter = _FakeAdapter(handler);
  return IrisTrackingRepository(dio);
}

Uint8List _frameBytes() => Uint8List.fromList([1, 2, 3, 4]);

void main() {
  test('a 422 response surfaces the backend reason, not unavailability', () async {
    final repository = _repository(
      (options) => ResponseBody.fromString(
        '{"error": "IRIS_TRACKING_FAILED", "message": "The live eye ROI or '
        'iris segmentation stage failed.", "reason": "ValueError: bad geometry"}',
        422,
        headers: {
          Headers.contentTypeHeader: [Headers.jsonContentType],
        },
      ),
    );

    await expectLater(
      repository.track(_frameBytes()),
      throwsA(
        isA<IrisTrackingFailedException>()
            .having(
              (error) => error.message,
              'message',
              'The live eye ROI or iris segmentation stage failed.',
            )
            .having(
              (error) => error.reason,
              'reason',
              'ValueError: bad geometry',
            ),
      ),
    );
  });

  test('a 4xx response without a reason still carries the message', () async {
    final repository = _repository(
      (options) => ResponseBody.fromString(
        '{"message": "The uploaded tracking frame is too large."}',
        413,
        headers: {
          Headers.contentTypeHeader: [Headers.jsonContentType],
        },
      ),
    );

    await expectLater(
      repository.track(_frameBytes()),
      throwsA(
        isA<IrisTrackingFailedException>().having(
          (error) => error.message,
          'message',
          'The uploaded tracking frame is too large.',
        ),
      ),
    );
  });

  test('a connection error is reported as backend unavailable', () async {
    final repository = _repository((options) {
      throw DioException.connectionError(
        requestOptions: options,
        reason: 'connection refused',
      );
    });

    await expectLater(
      repository.track(_frameBytes()),
      throwsA(isA<IrisTrackingUnavailableException>()),
    );
  });

  test('a 5xx response is reported as backend unavailable', () async {
    final repository = _repository(
      (options) => ResponseBody.fromString('{"message": "boom"}', 503),
    );

    await expectLater(
      repository.track(_frameBytes()),
      throwsA(
        isA<IrisTrackingUnavailableException>().having(
          (error) => error.message,
          'message',
          contains('HTTP 503'),
        ),
      ),
    );
  });

  test('a 422 followed by a 200 recovers and parses the tracking result', () async {
    // Sequence from the field report: first frame fails to process, the next
    // one succeeds. The second call must return a normal result so the UI
    // can leave the failure state immediately.
    var callCount = 0;
    final repository = _repository((options) {
      callCount += 1;
      if (callCount == 1) {
        return ResponseBody.fromString(
          '{"error": "IRIS_TRACKING_FAILED", "message": "failed"}',
          422,
          headers: {
            Headers.contentTypeHeader: [Headers.jsonContentType],
          },
        );
      }
      return ResponseBody.fromString(
        '{"data": {"detected": true, "confidence": 0.9, '
        '"frame_width": 640, "frame_height": 480, '
        '"eyes": [{"eye_side": "LEFT", "detected": true, "confidence": 0.9, '
        '"center_x": 10, "center_y": 20, "iris_width": 40, "iris_height": 36, '
        '"radius": 18, "circularity": 0.9}]}}',
        200,
        headers: {
          Headers.contentTypeHeader: [Headers.jsonContentType],
        },
      );
    });

    await expectLater(
      repository.track(_frameBytes()),
      throwsA(isA<IrisTrackingFailedException>()),
    );
    final frame = await repository.track(_frameBytes());
    expect(callCount, 2);
    expect(frame.detected, isTrue);
    expect(frame.eyes, isNotEmpty);
  });
}
