import os
import re
import datetime
import time
import numpy as np
import sounddevice as sd
from queue import Queue
from threading import Thread
from colorama import Fore, Style, init
import speech_recognition as sr
from google.cloud import texttospeech
from dotenv import load_dotenv
from openai import OpenAI
import pvporcupine
from scipy.io import wavfile

# Load environment variables from a .env file
load_dotenv()

# Global options
KEY_WORD = "Hey Magi"  # Replace with the actual keyword you have a model for
SPEAKING_RATE = 1.15
VOICE_NAME = "en-US-Polyglot-1"
PITCH = -5.0
OUTPUT_AUDIO_FILE = 'output.wav'
NOISE_CALIBRATION_TIME = 5
COMMAND_AWAIT_TIME_OUT = 10

RECORDINGS_DIR = 'recordings'
if not os.path.exists(RECORDINGS_DIR):
    os.makedirs(RECORDINGS_DIR)

# Set up your API keys
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
GOOGLE_CREDENTIALS = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
PORCUPINE_ACCESS_KEY = os.getenv('PORCUPINE_ACCESS_KEY')

# Initialize OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Initialize Google Text-to-Speech client
tts_client = texttospeech.TextToSpeechClient.from_service_account_json(GOOGLE_CREDENTIALS)

# Initialize colorama
init(autoreset=True)

# Initialize Speech Queue
speech_queue = Queue()

# Initialize the recognizer
recognizer = sr.Recognizer()

# Initialize Conversation History
conversation_history = []

# Initialize Noise Threshold
ambient_noise_energy_threshold = None


# Custom logging function with timestamps and keyword highlighting
def log(message, highlight=False):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if highlight:
        # Use regular expressions with word boundaries for case-insensitive replacement
        pattern = r'\b' + re.escape(KEY_WORD) + r'\b'
        message = re.sub(pattern, f"{Fore.GREEN}{KEY_WORD}{Style.RESET_ALL}{Fore.LIGHTBLACK_EX}", message, flags=re.IGNORECASE)
    print(f"{Fore.LIGHTBLACK_EX}[{timestamp}] {message}{Style.RESET_ALL}")


def play_acknowledgment_sound(ack_sound_file):
    try:
        # Read the audio file
        fs, data = wavfile.read(ack_sound_file)
        # Play the audio file
        sd.play(data, fs)
    except Exception as e:
        log(f"Error playing acknowledgment sound: {e}")


def calibrate_for_ambient_noise():
    global ambient_noise_energy_threshold
    with sr.Microphone() as source:
        log(f"Calibrating for ambient noise ({NOISE_CALIBRATION_TIME}s)... ")
        recognizer.adjust_for_ambient_noise(source, duration=NOISE_CALIBRATION_TIME)
        ambient_noise_energy_threshold = recognizer.energy_threshold
        log(f"Calibrated energy threshold: {ambient_noise_energy_threshold}")




# Initialize Porcupine wake word engine
porcupine = None
keyword_path = os.path.join(os.path.dirname(__file__), "Magi-wake.ppn")

def listen_for_wake_word():
    global porcupine
    porcupine = pvporcupine.create(access_key=PORCUPINE_ACCESS_KEY, keyword_paths=[keyword_path])

    def callback(indata, frames, time, status):
        if status:
            log(f"Error: {status}")
        # Convert the input data to 16-bit integers
        if indata.dtype != np.int16:
            indata = (indata * 32767).astype(np.int16)
        keyword_index = porcupine.process(indata.flatten())
        if keyword_index >= 0:
            log(f"Keyword '{KEY_WORD}' detected, listening for command...")
            # Play the acknowledgment sound
            play_acknowledgment_sound('acknowledgment.wav')
            speech_queue.put(True)  # Signal that the wake word was detected

    with sd.InputStream(callback=callback,
                        blocksize=porcupine.frame_length,
                        samplerate=porcupine.sample_rate,
                        channels=1):
        log(f"Listening for keyword '{KEY_WORD}'...")
        while True:
            time.sleep(0.1)


def recognize_speech():
    with sr.Microphone() as source:
        log("Please speak your command...")
        recognizer.energy_threshold = ambient_noise_energy_threshold
        try:
            audio = recognizer.listen(source, timeout=COMMAND_AWAIT_TIME_OUT)

            text = recognizer.recognize_google(audio)
            log("Processed Audio: " + text)

            # Save the audio data to a file in the 'recordings' directory
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            audio_filename = os.path.join(RECORDINGS_DIR, f"audio_{timestamp}.wav")
            with open(audio_filename, "wb") as audio_file:
                audio_file.write(audio.get_wav_data())
            log(f"Audio saved to {audio_filename}")
            
            return text
        except sr.WaitTimeoutError:
            log("No speech was detected within the timeout period.")
        except sr.UnknownValueError:
            log("Google Speech Recognition could not understand audio")
        except sr.RequestError as e:
            log(f"Could not request results from Google Speech Recognition service; {e}")
    return None


def process_command(command):
    conversation_history.append({"role": "user", "content": command})
    try:
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo-1106",
            messages=conversation_history
        )
        assistant_reply = response.choices[0].message.content
        conversation_history.append({"role": "assistant", "content": assistant_reply})
        log("Assistant Response: " + assistant_reply)
        return assistant_reply
    except Exception as e:
        log(f"Error querying OpenAI: {e}")
    return "I'm sorry, I can't process your request right now."


def synthesize_speech(text):
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        name=VOICE_NAME
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        pitch=PITCH,
        speaking_rate=SPEAKING_RATE
    )
    try:
        response = tts_client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )
        log("Speech synthesized successfully")
        return response.audio_content
    except Exception as e:
        log(f"Error synthesizing speech: {e}")
    return None



def play_speech(audio_content):
    if audio_content:
        with open(OUTPUT_AUDIO_FILE, 'wb') as out:
            out.write(audio_content)
        fs, data = wavfile.read(OUTPUT_AUDIO_FILE)
        log("Playing speech...")
        sd.play(data, fs)
        sd.wait()


def main():
    wake_word_thread = Thread(target=listen_for_wake_word)
    wake_word_thread.daemon = True
    wake_word_thread.start()

    try:
        while True:
            # Wait for the wake word to be detected
            speech_queue.get()
            command = recognize_speech()
            if command:
                play_acknowledgment_sound('acknowledgment.wav')
                response = process_command(command)
                audio_content = synthesize_speech(response)
                play_speech(audio_content)
            speech_queue.task_done()
    except KeyboardInterrupt:
        log("Exiting program...")
    finally:
        if porcupine is not None:
            porcupine.delete()

if __name__ == "__main__":
    calibrate_for_ambient_noise()
    main()