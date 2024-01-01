import pvporcupine
import numpy as np
import sounddevice as sd
from utils import log, vlog, vvlog

class WakeWordDetector:
    def __init__(self, config):
        self.config = config
        self.porcupine = None
        self.keyword_path = self.config.custom_wake_word_file
        self.access_key = self.config.porcupine_access_key
        self.detected_callback = None

    def init_porcupine(self):
        try:
            self.porcupine = pvporcupine.create(access_key=self.access_key, keyword_paths=[self.keyword_path])
        except Exception as e:
            log(f"Failed to initialize Porcupine: {e}", error=True)
            raise

    def listen_for_wake_word(self, detected_callback):
        self.detected_callback = detected_callback
        self.init_porcupine()

        def callback(indata, frames, time, status):
            if status:
                log(f"Error: {status}", error=True)
            if indata.dtype != np.int16:
                indata = (indata * 32767).astype(np.int16)
            keyword_index = self.porcupine.process(indata.flatten())
            if keyword_index >= 0:
                log(f"Keyword '{self.config.key_word}' detected.")
                if self.detected_callback:
                    self.detected_callback()

        with sd.InputStream(callback=callback,
                            blocksize=self.porcupine.frame_length,
                            samplerate=self.porcupine.sample_rate,
                            channels=1):
            log(f"Listening for keyword '{self.config.key_word}'...")
            sd.sleep(-1)  # Keep the stream open

    def shutdown(self):
        if self.porcupine is not None:
            self.porcupine.delete()