import speech_recognition as sr
from utils import log, vlog, vvlog

class SpeechRecognizer:
    def __init__(self, config):
        self.config = config
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = self.config.recognizer_pause_threshold
        self.recognizer.phrase_threshold = self.config.recognizer_phrase_threshold
        self.recognizer.non_speaking_duration = self.config.recognizer_non_speaking_duration
        self.ambient_noise_energy_threshold = None

    def calibrate_for_ambient_noise(self, source):
        log(f"Calibrating for ambient noise ({self.config.noise_calibration_time}s)...")
        self.recognizer.adjust_for_ambient_noise(source, duration=self.config.noise_calibration_time)
        self.ambient_noise_energy_threshold = self.recognizer.energy_threshold
        log(f"Calibrated energy threshold: {self.ambient_noise_energy_threshold}")

    def recognize_speech(self, source, timeout):
        log("Please speak your command...")
        self.recognizer.energy_threshold = self.ambient_noise_energy_threshold
        try:
            audio = self.recognizer.listen(source, timeout=timeout)
            text = self.recognizer.recognize_google(audio)
            log("Processed Audio: " + text)
            return text
        except sr.WaitTimeoutError:
            log("No speech was detected within the timeout period.", error=True)
        except sr.UnknownValueError:
            log("Google Speech Recognition could not understand audio", error=True)
        except sr.RequestError as e:
            log(f"Could not request results from Google Speech Recognition service; {e}", error=True)
        return None