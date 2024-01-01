import os
from dotenv import load_dotenv

class Config:
    def __init__(self):
        self.load_env_variables()

    def load_env_variables(self):
        # Load environment variables from a .env file
        load_dotenv()

        # Set up API keys and other configurations
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.google_credentials = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        self.porcupine_access_key = os.getenv('PORCUPINE_ACCESS_KEY')
        self.openweathermap_api_key = os.getenv('OPENWEATHERMAP_API_KEY')

        # Voice and speech configurations
        self.speaking_rate = 1.15
        self.voice_name = "en-US-Polyglot-1"
        self.pitch = -5.0
        self.output_audio_file = 'output.wav'

        # Recognition configurations
        self.noise_calibration_time = 2
        self.command_await_timeout = 10
        self.recognizer_pause_threshold = 0.5
        self.recognizer_phrase_threshold = 0.3
        self.recognizer_non_speaking_duration = 0.2

        # Wake word configurations
        self.key_word = "Hey Magi"
        self.custom_wake_word_file = "Magi-wake.ppn"

        # Directories
        self.recordings_directory = 'recordings'
        self.outputs_directory = 'outputs'
        self.system_prompt_file = "system.txt"

        # Ensure necessary directories exist
        if not os.path.exists(self.recordings_directory):
            os.makedirs(self.recordings_directory)