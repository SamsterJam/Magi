import threading
import signal
import speech_recognition as sr
from config import Config
from audio_manager import AudioManager
from speech_recognizer import SpeechRecognizer
from text_to_speech import TextToSpeech
from openai_client import OpenAIClient
from wake_word_detector import WakeWordDetector
from assistant_functions import get_weather
from utils import log, vlog, vvlog


class VoiceAssistant:
    def __init__(self):
        self.shutdown_flag = False
        self.config = Config()
        self.audio_manager = AudioManager()
        self.speech_recognizer = SpeechRecognizer(self.config)
        self.text_to_speech = TextToSpeech(self.config)
        self.openai_client = OpenAIClient(self.config)
        self.wake_word_detector = WakeWordDetector(self.config)
        self.setup_signal_handling()

    def setup_signal_handling(self):
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, sig, frame):
        log("Shutdown initiated by signal...")
        self.shutdown_flag = True

    def run(self):
        try:
            # Initialize the wake word detector
            self.wake_word_detector.init_porcupine()

            # Calibrate the recognizer for ambient noise before starting the main loop
            with sr.Microphone() as source:
                self.speech_recognizer.calibrate_for_ambient_noise(source)

            # Start the wake word detector in a separate thread
            wake_word_thread = threading.Thread(target=self.wake_word_detector.listen_for_wake_word, args=(self.wake_word_detected,))
            wake_word_thread.start()

            log("Voice Assistant is running. Say the wake word to activate.")
            while not self.shutdown_flag:
                # Main loop logic placeholder
                pass
        finally:
            self.cleanup()

    def wake_word_detected(self):
        log("Wake word detected.")
        # Play a sound to acknowledge wake word detection
        self.audio_manager.play_sound('Sounds/Wake.wav', wait_full_sound=True)
        # Capture and process the command
        self.process_command()

    def process_command(self):
        with self.speech_recognizer.recognizer.Microphone() as source:
            command = self.speech_recognizer.recognize_speech(source, self.config.command_await_timeout)
            if command:
                self.handle_command(command)

    def handle_command(self, command):
        # Check for local commands such as "shutdown"
        if command.lower() == "shutdown":
            self.shutdown()
            return

        # Process command with OpenAI or other functionalities
        response = self.openai_client.process_command_with_assistant(command)
        if response:
            audio_content = self.text_to_speech.synthesize_speech(response)
            self.audio_manager.play_sound(audio_content)

    def cleanup(self):
        log("Cleaning up resources...")
        self.wake_word_detector.shutdown()
        self.audio_manager.shutdown()
        # Additional cleanup logic as needed

    def shutdown(self):
        log("Shutdown initiated...")
        self.shutdown_flag = True
        # Play a sound to acknowledge shutdown command
        self.audio_manager.play_sound('Sounds/Shutdown.wav', wait_full_sound=True)