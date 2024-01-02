import speech_recognition as sr
import datetime
import os
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
        vlog(f"Calibrated energy threshold: {self.ambient_noise_energy_threshold}")

    def recognize_speech(self, source, timeout):
        log("Listening, speak your command...")
        try:
            audio = self.recognizer.listen(source, timeout=timeout)
            vvlog("Picking up audio...")

            text = self.recognizer.recognize_google(audio)
            log("Processed Audio: " + text)

            # Save the audio data to a file in the 'recordings' directory
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            audio_filename = os.path.join(self.config.recordings_directory, f"audio_{timestamp}.wav")
            with open(audio_filename, "wb") as audio_file:
                audio_file.write(audio.get_wav_data())
            vlog(f"Audio saved to {audio_filename}")

            return text
        except sr.WaitTimeoutError:
            log("No speech was detected within the timeout period.", error=True)
        except sr.UnknownValueError:
            log("Google Speech Recognition could not understand audio", error=True)
        except sr.RequestError as e:
            log(f"Could not request results from Google Speech Recognition service; {e}", error=True)
        return None