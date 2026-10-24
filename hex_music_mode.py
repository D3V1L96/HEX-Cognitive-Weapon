import logging
import threading
import time
import math

logging.basicConfig(level=logging.INFO, format='[Music] %(message)s')
logger = logging.getLogger(__name__)


class MusicVisualizerData:
    def __init__(self):
        self.bands = [0.0] * 16
        self.smooth_bands = [0.0] * 16
        self.volume = 0.0
        self.smooth_volume = 0.0
        self.beat = False
        self.is_active = False
        self.lock = threading.Lock()
        self.attack = 0.35
        self.decay = 0.08
        self.vol_attack = 0.3
        self.vol_decay = 0.05

    def update(self, raw_bands, raw_volume, beat=False):
        with self.lock:
            self.bands = raw_bands[:]
            self.volume = raw_volume
            self.beat = beat
            for i in range(16):
                target = raw_bands[i]
                if target > self.smooth_bands[i]:
                    self.smooth_bands[i] += (target - self.smooth_bands[i]) * self.attack
                else:
                    self.smooth_bands[i] += (target - self.smooth_bands[i]) * self.decay
            if raw_volume > self.smooth_volume:
                self.smooth_volume += (raw_volume - self.smooth_volume) * self.vol_attack
            else:
                self.smooth_volume += (raw_volume - self.smooth_volume) * self.vol_decay

    def get_bands(self):
        with self.lock:
            return self.smooth_bands[:], self.smooth_volume, self.beat


class AudioCapture:
    def __init__(self, visualizer_data):
        self.data = visualizer_data
        self.running = False
        self.thread = None
        self.sample_rate = 22050      # Lower sample rate = less buffer pressure
        self.chunk_size = 2048        # Smaller chunk = no stack overflow

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        logger.info("Audio Capture Started")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=3)
        self.data.update([0.0] * 16, 0.0, False)
        logger.info("Audio Capture Stopped")

    def _capture_loop(self):
        """Crash-proof audio capture with full error isolation."""
        np = None
        sd = None

        try:
            import numpy as _np
            import sounddevice as _sd
            np = _np
            sd = _sd
        except ImportError:
            logger.warning("sounddevice/numpy not installed. Using simulated visualizer.")
            self._fake_visualizer_loop()
            return

        # Find loopback device safely
        loopback_device = None
        try:
            devices = sd.query_devices()
            for i, d in enumerate(devices):
                name_lower = d['name'].lower()
                if 'loopback' in name_lower or 'stereo mix' in name_lower:
                    loopback_device = i
                    break
            if loopback_device is None:
                for i, d in enumerate(devices):
                    if d.get('hostapi', -1) == 3 and d['max_output_channels'] > 0:
                        loopback_device = i
                        break
        except Exception as e:
            logger.error(f"Device enumeration failed: {e}")
            self._fake_visualizer_loop()
            return

        if loopback_device is None:
            logger.warning("No loopback device found. Using simulated visualizer.")
            self._fake_visualizer_loop()
            return

        logger.info(f"Audio device: {devices[loopback_device]['name']}")

        hann_window = np.hanning(self.chunk_size)
        freq_bins = np.fft.rfftfreq(self.chunk_size, 1.0 / self.sample_rate)
        band_edges = [0, 60, 120, 250, 500, 1000, 2000, 3000, 4000,
                      5000, 6000, 7000, 8000, 10000, 12000, 15000, 22050]
        prev_energy = 0.0
        energy_history = []
        consecutive_errors = 0

        while self.running:
            if not self.data.is_active:
                time.sleep(0.05)
                continue

            try:
                # Use shorter timeout to prevent blocking crash
                audio_data = sd.rec(
                    frames=self.chunk_size,
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype='float32',
                    device=loopback_device,
                    blocking=True
                )

                # Validate data before processing
                if audio_data is None or len(audio_data) == 0:
                    time.sleep(0.02)
                    continue

                samples = audio_data.flatten()

                # Check for invalid values
                if not np.isfinite(samples).all():
                    time.sleep(0.02)
                    continue

                windowed = samples * hann_window
                rms = float(np.sqrt(np.mean(samples ** 2)))
                volume = min(rms * 4.0, 1.0)

                fft = np.abs(np.fft.rfft(windowed))

                bands = []
                for i in range(16):
                    low = band_edges[i]
                    high = band_edges[i + 1]
                    mask = (freq_bins >= low) & (freq_bins < high)
                    if np.any(mask):
                        band_energy = float(np.mean(fft[mask]))
                        scaled = math.log1p(band_energy * 0.005) / math.log1p(50)
                        bands.append(min(max(scaled, 0.0), 1.0))
                    else:
                        bands.append(0.0)

                current_energy = sum(bands[:6]) / 6
                energy_history.append(current_energy)
                if len(energy_history) > 30:
                    energy_history.pop(0)

                avg_energy = sum(energy_history) / len(energy_history) if energy_history else 0
                beat = (current_energy > avg_energy * 1.4 and
                        current_energy > prev_energy * 1.2 and
                        volume > 0.1)
                prev_energy = current_energy

                self.data.update(bands, volume, beat)
                consecutive_errors = 0

            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors <= 3:
                    logger.debug(f"Capture error ({consecutive_errors}): {e}")
                time.sleep(0.05)

                # If too many errors, switch to fake visualizer
                if consecutive_errors > 20:
                    logger.warning("Too many capture errors. Switching to simulated visualizer.")
                    self._fake_visualizer_loop()
                    return

        logger.info("Audio capture loop ended normally")

    def _fake_visualizer_loop(self):
        """Simulated visualizer - always works, never crashes."""
        logger.info("Running simulated visualizer")
        t_offset = time.time()

        while self.running:
            if not self.data.is_active:
                time.sleep(0.05)
                continue

            try:
                t = time.time() - t_offset
                bands = []
                for i in range(16):
                    base_freq = 0.8 + i * 0.3
                    val = abs(math.sin(t * base_freq + i * 0.5)) * 0.5
                    val += abs(math.sin(t * 1.7 + i * 0.3)) * 0.3
                    val += abs(math.sin(t * 3.1 + i * 0.8)) * 0.2
                    pulse = max(0, math.sin(t * 2.0)) ** 3
                    val = val * 0.7 + pulse * 0.3
                    bands.append(min(val, 1.0))

                volume = sum(bands[:6]) / 6
                beat = volume > 0.65 and abs(math.sin(t * 2.0)) > 0.95

                self.data.update(bands, volume, beat)
                time.sleep(0.033)

            except Exception:
                time.sleep(0.1)


music_data = MusicVisualizerData()
audio_capture = AudioCapture(music_data)