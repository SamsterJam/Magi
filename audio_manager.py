import sounddevice as sd
from scipy.io import wavfile
from queue import Queue
import threading
from utils import log, vlog, vvlog


class AudioManager:
    def __init__(self):
        self.playback_queue = Queue()
        self.playback_thread = threading.Thread(target=self._playback_worker, daemon=True)
        self.playback_event = threading.Event()
        self.playback_thread.start()

    def _playback_worker(self):
        while True:
            sound_file, wait_full_sound = self.playback_queue.get()
            if sound_file is None:
                break  # Stop the thread if None is enqueued
            try:
                fs, data = wavfile.read(sound_file)
                sd.play(data, fs)
                if wait_full_sound:
                    sd.wait()
            except Exception as e:
                log(f"Error playing sound: {e}", error=True)
            finally:
                self.playback_queue.task_done()
                self.playback_event.set()  # Signal that playback is done

    def play_sound(self, sound_file, wait_full_sound=False):
        self.playback_event.clear()  # Reset the event
        self.playback_queue.put((sound_file, wait_full_sound))
        if wait_full_sound:
            self.playback_event.wait()  # Wait for the sound to finish playing

    def stop_all_sounds(self):
        sd.stop()

    def shutdown(self):
        self.playback_queue.put((None, False))  # Enqueue None to stop the thread
        self.playback_thread.join()