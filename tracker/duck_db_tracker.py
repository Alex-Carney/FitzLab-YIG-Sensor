import time
import datetime
import numpy as np
import duckdb
from qcodes.instrument_drivers.signal_hound import SignalHoundUSBSA124B

# ============================================================
# CONFIG
# ============================================================
INITIAL_CENTER_FREQ = 6.46335e9    # Hz
SPAN                = 5e6          # Hz
RBW                 = 30e3         # Hz
VBW                 = 30e3         # Hz
AVERAGES            = 5

SAMPLE_INTERVAL_SEC = 1            # cadence between traces

# Total runtime. Set to None to run forever (until Ctrl-C).
TOTAL_DURATION_SEC  = 60 * 60 * 24   # 24 hours

# Retune when |peak - center| exceeds this fraction of (span/2).
RETUNE_THRESHOLD_FRAC = 0.5

# Don't chase noise: only retune if the peak sits at least this many dB
# above the median of the trace.
PEAK_SNR_MIN_DB = 6.0

DB_PATH    = "spectrum_data_ovn.duckdb"
TABLE_NAME = "spectra"

# Verify on the first trace that SA's frequency axis matches
# linspace(center - span/2, center + span/2, n_points).
# If yes, we can safely reconstruct freqs on read instead of storing them.
VERIFY_FREQ_AXIS = True
FREQ_AXIS_TOL_HZ = 1.0             # reconstruction must match to within this
# ============================================================


def setup_spectrum_analyzer(center_freq, span, rbw, vbw, avg):
    sh = SignalHoundUSBSA124B("mysignalhound")
    sh.frequency(center_freq)
    sh.span(span)
    sh.rbw(rbw)
    sh.vbw(vbw)
    sh.configure()
    sh.avg(avg)
    return sh


def retune(sh, new_center, span, rbw, vbw, avg):
    sh.frequency(new_center)
    sh.span(span)
    sh.rbw(rbw)
    sh.vbw(vbw)
    sh.configure()
    sh.avg(avg)


def init_db(db_path, table_name):
    conn = duckdb.connect(db_path)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            time_created TIMESTAMP,
            center_freq  DOUBLE,
            span         DOUBLE,
            rbw          DOUBLE,
            n_points     INTEGER,
            powers       FLOAT[]
        )
    """)
    return conn


def insert_trace(conn, table_name, t, center_freq, span, rbw, n_points, powers):
    conn.execute(
        f"INSERT INTO {table_name} VALUES (?, ?, ?, ?, ?, ?)",
        [t, center_freq, span, rbw, n_points,
         powers.astype(np.float32).tolist()],
    )


def verify_frequency_axis(freqs, center_freq, span, tol_hz):
    """Confirm freqs matches linspace(center - span/2, center + span/2, N)."""
    n = len(freqs)
    reconstructed = np.linspace(center_freq - span / 2,
                                center_freq + span / 2, n)
    max_err = np.max(np.abs(np.asarray(freqs) - reconstructed))
    return max_err < tol_hz, max_err


def find_peak(freqs, powers, center_freq, snr_min_db):
    """Return (peak_freq, offset_from_center_hz, trusted)."""
    idx = int(np.argmax(powers))
    peak_freq  = float(freqs[idx])
    peak_power = float(powers[idx])
    noise      = float(np.median(powers))
    trusted    = (peak_power - noise) >= snr_min_db
    return peak_freq, peak_freq - center_freq, trusted


def format_duration(seconds):
    """Format seconds as a human-readable string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds/60:.1f} min"
    if seconds < 86400:
        return f"{seconds/3600:.2f} hr"
    return f"{seconds/86400:.2f} days"


def main():
    print(f"Opening DB at {DB_PATH}")
    conn = init_db(DB_PATH, TABLE_NAME)

    print(f"Setting up SA at {INITIAL_CENTER_FREQ/1e9:.6f} GHz, "
          f"span={SPAN/1e6:.2f} MHz, RBW={RBW/1e3:.1f} kHz")
    sh = setup_spectrum_analyzer(INITIAL_CENTER_FREQ, SPAN, RBW, VBW, AVERAGES)
    current_center = INITIAL_CENTER_FREQ

    retune_limit_hz = RETUNE_THRESHOLD_FRAC * (SPAN / 2.0)
    print(f"Retune trigger: |offset| > {retune_limit_hz/1e6:.3f} MHz from center")

    if TOTAL_DURATION_SEC is not None:
        n_expected = TOTAL_DURATION_SEC / SAMPLE_INTERVAL_SEC
        print(f"Will run for {format_duration(TOTAL_DURATION_SEC)} "
              f"(~{n_expected:.0f} traces at {SAMPLE_INTERVAL_SEC}s interval)")
    else:
        print(f"Running forever (until Ctrl-C), "
              f"trace every {SAMPLE_INTERVAL_SEC}s")

    start_time         = time.time()
    freq_axis_verified = False
    n                  = 0
    slow_loop_count    = 0

    try:
        while True:
            if TOTAL_DURATION_SEC is not None and \
               (time.time() - start_time) >= TOTAL_DURATION_SEC:
                print(f"\nReached {format_duration(TOTAL_DURATION_SEC)} "
                      f"duration. Stopping.")
                break

            loop_start = time.time()

            powers = np.asarray(sh.trace())
            freqs  = np.asarray(sh.frequency_axis())
            t_now  = datetime.datetime.now()

            # One-time sanity check that the SA's freq axis matches the
            # linspace reconstruction we'll use on read.
            if VERIFY_FREQ_AXIS and not freq_axis_verified:
                ok, err = verify_frequency_axis(
                    freqs, current_center, SPAN, FREQ_AXIS_TOL_HZ
                )
                if ok:
                    print(f"  Freq axis verified (max reconstruction "
                          f"error {err:.3f} Hz). Storing powers only.")
                else:
                    print(f"  WARNING: freq axis deviates by {err:.3f} Hz "
                          f"from linspace reconstruction. Reading back "
                          f"with linspace will be slightly off.")
                freq_axis_verified = True

            insert_trace(conn, TABLE_NAME, t_now,
                         current_center, SPAN, RBW, len(powers), powers)
            n += 1

            peak_freq, offset, trusted = find_peak(
                freqs, powers, current_center, PEAK_SNR_MIN_DB
            )

            elapsed_total = time.time() - start_time
            if TOTAL_DURATION_SEC is not None:
                progress = f" [{format_duration(elapsed_total)}/" \
                           f"{format_duration(TOTAL_DURATION_SEC)}]"
            else:
                progress = f" [{format_duration(elapsed_total)} elapsed]"

            print(
                f"[{t_now.isoformat(timespec='seconds')}] "
                f"#{n}{progress}  center={current_center/1e9:.6f} GHz  "
                f"peak={peak_freq/1e9:.6f} GHz  "
                f"offset={offset/1e3:+.1f} kHz  "
                f"trusted={trusted}"
            )

            # Retune if drift is significant and the peak is real
            if trusted and abs(offset) > retune_limit_hz:
                new_center = peak_freq
                print(f"  -> RETUNING to {new_center/1e9:.6f} GHz "
                      f"(drift {offset/1e6:+.3f} MHz)")
                retune(sh, new_center, SPAN, RBW, VBW, AVERAGES)
                current_center = new_center

            loop_elapsed = time.time() - loop_start
            remaining    = SAMPLE_INTERVAL_SEC - loop_elapsed
            if remaining > 0:
                time.sleep(remaining)
            else:
                slow_loop_count += 1
                print(f"  (warning: loop took {loop_elapsed:.2f}s "
                      f"> {SAMPLE_INTERVAL_SEC}s interval)")

    except KeyboardInterrupt:
        print(f"\nInterrupted by user.")
    finally:
        total_elapsed = time.time() - start_time
        print(f"{n} traces written to {DB_PATH} "
              f"over {format_duration(total_elapsed)}")
        if slow_loop_count > 0:
            print(f"{slow_loop_count} loop(s) exceeded "
                  f"{SAMPLE_INTERVAL_SEC}s interval")
        try:
            sh.close()
        except Exception as e:
            print(f"Error closing SA: {e}")
        conn.close()


if __name__ == "__main__":
    main()