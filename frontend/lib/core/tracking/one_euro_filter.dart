import 'dart:math' as math;

class OneEuroFilter {
  OneEuroFilter({
    this.initialFrequency = 30,
    this.minCutoff = 1.5,
    this.beta = 0.01,
    this.derivativeCutoff = 1,
  }) : assert(initialFrequency > 0),
       assert(minCutoff > 0),
       assert(derivativeCutoff > 0);

  final double initialFrequency;
  final double minCutoff;
  final double beta;
  final double derivativeCutoff;

  double? _filteredValue;
  double? _filteredDerivative;
  double? _lastRawValue;
  double? _lastTimestampSeconds;

  double filter(double value, double timestampSeconds) {
    final lastTimestamp = _lastTimestampSeconds;
    final elapsed = lastTimestamp == null
        ? 1 / initialFrequency
        : timestampSeconds - lastTimestamp;
    final frequency = elapsed > 0.000001 ? 1 / elapsed : initialFrequency;
    final previousRaw = _lastRawValue;
    final derivative = previousRaw == null
        ? 0.0
        : (value - previousRaw) * frequency;
    final derivativeAlpha = _alpha(derivativeCutoff, frequency);
    final filteredDerivative = _lowPass(
      derivative,
      _filteredDerivative,
      derivativeAlpha,
    );
    final cutoff = minCutoff + (beta * filteredDerivative.abs());
    final filtered = _lowPass(value, _filteredValue, _alpha(cutoff, frequency));

    _lastRawValue = value;
    _lastTimestampSeconds = timestampSeconds;
    _filteredDerivative = filteredDerivative;
    _filteredValue = filtered;
    return filtered;
  }

  void reset() {
    _filteredValue = null;
    _filteredDerivative = null;
    _lastRawValue = null;
    _lastTimestampSeconds = null;
  }

  double _alpha(double cutoff, double frequency) {
    final period = 1 / frequency;
    final timeConstant = 1 / (2 * math.pi * cutoff);
    return 1 / (1 + (timeConstant / period));
  }

  double _lowPass(double value, double? previous, double alpha) {
    return previous == null
        ? value
        : (alpha * value) + ((1 - alpha) * previous);
  }
}
