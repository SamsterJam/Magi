import threading
import signal
import speech_recognition as sr
import time
from config import Config
from audio_manager import AudioManager
from speech_recognizer import SpeechRecognizer
from text_to_speech import TextToSpeech
from openai_client import OpenAIClient
from wake_word_detector import WakeWordDetector
from assistant_functions import get_weather
from utils import log, vlog, vvlog
import openai_client


class VoiceAssistant:
    def __init__(self):
        vvlog("Initializing Voice Assistant...")
        self.shutdown_flag = False
        self.config = Config()
        self.audio_manager = AudioManager()
        self.speech_recognizer = SpeechRecognizer(self.config)
        self.text_to_speech = TextToSpeech(self.config)
        self.openai_client = OpenAIClient(self.config)
        self.wake_word_detector = WakeWordDetector(self.config)
        self.setup_signal_handling()

        # Close past threads and assistants
        vlog("Closing past threads and assistants...")
        self.openai_client.close_and_clear_files()

        # Create a thread and an assistant
        vlog("Creating new thread...")
        self.thread_id = self.openai_client.create_thread()

        with open("system-prompt.txt", 'r') as file:
            prompt = file.read()
            vvlog(f"Creating Assistant with prompt from 'system-prompt.txt'")
        
        vlog("Creating new assistant...")
        self.assistant_id = self.openai_client.create_assistant(prompt)
    
        self.command_actions = {
                "stop": self.stop_audio,
                "nevermind": self.cancel_command,
                "never mind": self.cancel_command,
                "cancel": self.cancel_command,
                "shutdown": self.shutdown,
                "shut down": self.shutdown,
            }

    def setup_signal_handling(self):
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, sig, frame):
        log("Shutdown initiated by signal...")
        self.shutdown_flag = True

    def run(self):
        try:
            # Initialize the wake word detector
            vvlog("Initializing Porcupine...")
            self.wake_word_detector.init_porcupine()

            # Calibrate the recognizer for ambient noise before starting the main loop
            with sr.Microphone() as source:
                self.speech_recognizer.calibrate_for_ambient_noise(source)

            # Start the wake word detector in a separate thread
            self.wake_word_thread = threading.Thread(target=self.wake_word_detector.listen_for_wake_word, args=(self.wake_word_detected,))
            self.wake_word_thread.start()
            vvlog("Wake-Word thread started!")

            log("Voice Assistant is running. Say the wake word to activate.")
            while not self.shutdown_flag:
                time.sleep(1)
        finally:
            self.cleanup()

    def wake_word_detected(self):
        # Play a sound to acknowledge wake word detection
        self.audio_manager.play_sound('Sounds/Wake.wav')

        # Capture and process the command
        self.process_command()

    def process_command(self):
        with sr.Microphone() as source:
            command = self.speech_recognizer.recognize_speech(source, self.config.command_await_timeout)
            if command:
                self.audio_manager.play_sound('Sounds/Heard.wav')
                self.handle_command(command)
            else:
                self.audio_manager.play_sound('Sounds/NoSpeech.wav')

    def handle_command(self, command):
        # Check for local commands such as "shutdown"
        if command.lower() in self.command_actions:
            vlog("Command issued is local command, executing corresponding function...")
            self.audio_manager.play_sound('Sounds/LocalCommand.wav')
            self.command_actions[command.lower()]()  # Execute the corresponding function
        else:
            self.audio_manager.play_sound('Sounds/Heard.wav', True)
            # Process command with OpenAI or other functionalities
            # Use the thread_id and assistant_id when calling process_command_with_assistant
            self.audio_manager.play_sound('Sounds/Request.wav')
            response = self.openai_client.process_command_with_assistant(self.thread_id, command, self.assistant_id)
            if response:
                self.audio_manager.play_sound('Sounds/Received.wav')
                # Assuming response is a list of MessageContentText objects, extract the text value
                if isinstance(response, list) and response and hasattr(response[0], 'text'):
                    text_response = response[0].text.value
                else:
                    text_response = str(response)  # Fallback to converting whatever response is to a string
                
                # Generate a unique filename for each synthesized speech
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                audio_file_path = self.text_to_speech.synthesize_speech(text_response, f"speech_{timestamp}.wav")
                
                if audio_file_path:
                    self.audio_manager.play_sound(audio_file_path)
    
    def stop_audio(self):
        self.audio_manager.stop_all_sounds()
        log("Audio stopped.")

    def cancel_command(self):
        log("Command cancelled.")
    
    def shutdown(self):
        log("Shutdown initiated...")
        self.shutdown_flag = True
        # Play a sound to acknowledge shutdown command
        self.audio_manager.play_sound('Sounds/Shutdown.wav', wait_full_sound=True)

    def cleanup(self):
        log("Cleaning up resources...")

        # Delete the thread and assistant
        if self.thread_id:
            self.openai_client.delete_thread(self.thread_id)
        if self.assistant_id:
            self.openai_client.delete_assistant(self.assistant_id)

        self.wake_word_detector.shutdown()

        if self.wake_word_thread.is_alive():
            self.wake_word_thread.join()  # Wait for the wake word thread to finish

        self.audio_manager.shutdown()