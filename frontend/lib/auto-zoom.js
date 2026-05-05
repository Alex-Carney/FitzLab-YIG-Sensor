// Pure auto-zoom math. Caller passes peak data and the latest row's full
// sweep; we return [low, high] in Hz. See spec §"Plot interaction model"
// for derivation.

export const SNR_FLOOR_DB    = 3.0;
export const MIN_BUFFER_HZ   = 2.0e6;   // per-side buffer when peak is stationary
export const BUFFER_FRACTION = 0.2;     // per-side buffer as fraction of motion

/**
 * @param {Array<{peak_freq:number, snr:number}>} peaks
 * @param {{center_freq:number, span:number} | null} latestRow  full-sweep fallback
 * @returns {[number, number] | null}  [low, high] in Hz, or null if no signal
 *          and no fallback.
 */
export function computeAutoFreqRange(peaks, latestRow) {
  const fullSpan = latestRow
    ? [latestRow.center_freq - latestRow.span / 2,
       latestRow.center_freq + latestRow.span / 2]
    : null;

  const good = (peaks || []).filter((p) => p && p.snr >= SNR_FLOOR_DB);
  if (good.length === 0) {
    return fullSpan;
  }

  let fMin = good[0].peak_freq;
  let fMax = good[0].peak_freq;
  for (const p of good) {
    if (p.peak_freq < fMin) fMin = p.peak_freq;
    if (p.peak_freq > fMax) fMax = p.peak_freq;
  }

  const motion = fMax - fMin;
  const buffer = Math.max(MIN_BUFFER_HZ, BUFFER_FRACTION * motion);
  let lo = fMin - buffer;
  let hi = fMax + buffer;
  if (fullSpan) {
    lo = Math.max(lo, fullSpan[0]);
    hi = Math.min(hi, fullSpan[1]);
  }
  return [lo, hi];
}
