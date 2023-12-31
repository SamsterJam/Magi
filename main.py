# === Imports === #

import os
import re
import datetime
import traceback
import time
import argparse
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





# === Global Options === #

KEY_WORD = "Hey Magi"
ASSISTANT_ID = "asst_9MSfQ82sD2yiU0iz5pPbcIEA"
CUSTOM_WAKE_WORD_FILE = "Magi-wake.ppn"
SPEAKING_RATE = 1.15
VOICE_NAME = "en-US-Polyglot-1"
PITCH = -5.0
OUTPUT_AUDIO_FILE = 'output.wav'
NOISE_CALIBRATION_TIME = 5
COMMAND_AWAIT_TIME_OUT = 10
RECORDINGS_DIR = 'recordings'

RECOGNIZER_PAUSE_THRESHOLD = 0.5
RECOGNIZER_PHRASE_THRESHOLD = 0.3
RECOGNIZER_NON_SPEAKING_DURATION = 0.2




# === API keys ===#

# Load environment variables from a .env file
load_dotenv()

# Set up your API keys
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
GOOGLE_CREDENTIALS = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
PORCUPINE_ACCESS_KEY = os.getenv('PORCUPINE_ACCESS_KEY')





# === Command-line argument parsing === #

parser = argparse.ArgumentParser(description="Log messages with optional verbosity.")
parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose logging')
args = parser.parse_args()





# === Initializations === #

def log(message, error=False):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    color = Fore.RED if error else Fore.RESET
    print(f"{color}[{timestamp}] {message}{Style.RESET_ALL}")

def vlog(message):
    if args.verbose:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{Fore.LIGHTBLACK_EX}[{timestamp}] {message}{Style.RESET_ALL}")
    
vlog("Initializing...")

# Initialize Recordings Folder
if not os.path.exists(RECORDINGS_DIR):
    os.makedirs(RECORDINGS_DIR)

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
recognizer.pause_threshold = RECOGNIZER_PAUSE_THRESHOLD
recognizer.phrase_threshold = RECOGNIZER_PHRASE_THRESHOLD
recognizer.non_speaking_duration = RECOGNIZER_NON_SPEAKING_DURATION

# Initialize Conversation History
conversation_history = []

with open("requirements.txt", "r") as file:
    data = file.read()

conversation_history.append({"role": "system", "content": data})

# Initialize Noise Threshold
ambient_noise_energy_threshold = None

# Global flag to indicate shutdown
shutdown_flag = False

vlog("Initialization Complete!")




# === Function Definitions === #

def play_feedback_sound(sound_file, waitFullSound=False):
    try:
        # Read the audio file
        fs, data = wavfile.read(sound_file)
        # Play the audio file
        sd.play(data, fs)
        if waitFullSound:
            sd.wait()
    except Exception as e:
        log(f"Error playing feedback sound: {e}", True)


def calibrate_for_ambient_noise():
    global ambient_noise_energy_threshold
    with sr.Microphone() as source:
        log(f"Calibrating for ambient noise ({NOISE_CALIBRATION_TIME}s)... ")
        recognizer.adjust_for_ambient_noise(source, duration=NOISE_CALIBRATION_TIME)
        ambient_noise_energy_threshold = recognizer.energy_threshold
        vlog(f"Calibrated energy threshold: {ambient_noise_energy_threshold}")


# Initialize Porcupine wake word engine
porcupine = None
keyword_path = os.path.join(os.path.dirname(__file__), CUSTOM_WAKE_WORD_FILE)

def listen_for_wake_word():
    global porcupine
    porcupine = pvporcupine.create(access_key=PORCUPINE_ACCESS_KEY, keyword_paths=[keyword_path])

    def callback(indata, frames, time, status):
        if status:
            log(f"Error: {status}", True)
        # Convert the input data to 16-bit integers
        if indata.dtype != np.int16:
            indata = (indata * 32767).astype(np.int16)
        keyword_index = porcupine.process(indata.flatten())
        if keyword_index >= 0:
            log(f"Keyword '{KEY_WORD}' detected, listening for command...")
            # Play the acknowledgment sound
            play_feedback_sound('Sounds/Wake.wav')
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
            vlog(f"Audio saved to {audio_filename}")
            
            return text
        except sr.WaitTimeoutError:
            log("No speech was detected within the timeout period.", True)
            play_feedback_sound("Sounds/NoSpeech.wav")
        except sr.UnknownValueError:
            log("Google Speech Recognition could not understand audio", True)
            play_feedback_sound("Sounds/NoSpeech.wav")
        except sr.RequestError as e:
            log(f"Could not request results from Google Speech Recognition service; {e}", True)
            play_feedback_sound("Sounds/Error.wav")
    return None


def process_command_with_assistant(thread_id, command):
    try:
        # Log the command received
        vlog(f"OpenAI: Received command: {command}")

        # Add the user's message to the thread
        vlog("OpenAI: Creating Message...")
        message = openai_client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=command
        )

        # Log the message ID
        vlog(f"Message created with ID: {message.id}")

        # Run the assistant on the thread
        vlog("OpenAI: Running Assistant with Thread...")
        run_response = openai_client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID  # Replace with your actual assistant ID
        )

        # Log the run ID
        vlog(f"Run created with ID: {run_response.id}")

        # Wait for the run to complete and get the assistant's response
        vlog("OpenAI: Waiting for Response Creation...")
        while True:
            run_status = openai_client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run_response.id
            )
            if run_status.status == 'completed':
                vlog("OpenAI: Created Response!")
                break
            time.sleep(1)  # Polling interval

        # Retrieve the assistant's messages
        vlog("OpenAI: Retrieving Response...")
        messages = openai_client.beta.threads.messages.list(
            thread_id=thread_id
        )
        vlog("OpenAI: Retrieved Response!")

        # Extract the text content from the assistant's last message
        assistant_messages = [msg for msg in messages.data if msg.role == 'assistant']
        # Sort the messages by the 'created_at' timestamp
        assistant_messages.sort(key=lambda msg: msg.created_at)
        if assistant_messages:
            # Get the last message from the assistant
            vlog(assistant_messages)
            assistant_reply_content = assistant_messages[-1].content
            if isinstance(assistant_reply_content, list) and assistant_reply_content:
                assistant_reply = assistant_reply_content[-1].text.value  # Get the last text value
            else:
                assistant_reply = "I'm sorry, I can't process your request right now."
        else:
            assistant_reply = "I'm sorry, I can't process your request right now."

        vlog(f"OpenAI: Returning Response: {assistant_reply}")
        return assistant_reply
    except Exception as e:
        log(f"Error during command processing: {e}", True)
        traceback.print_exc()


def synthesize_speech(text):
    vlog(f"Google-Synthesis: Initializing with text: '{text}'")
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
    vlog("Google-Synthesis: Initialized!")
    try:
        vlog("Google-Synthesis: Creating Response...")
        response = tts_client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )
        log("Speech synthesized successfully")
        vlog("Google-Synthesis: Returning Response...")
        return response.audio_content
    except Exception as e:
        log(f"Error synthesizing speech: {e}", True)
    return None



def play_speech(audio_content):
    if audio_content:
        with open(OUTPUT_AUDIO_FILE, 'wb') as out:
            out.write(audio_content)
        fs, data = wavfile.read(OUTPUT_AUDIO_FILE)
        log("Playing speech...")
        sd.play(data, fs)
        sd.wait()


def create_thread():
    vlog("Creating a new thread...")
    try:
        thread_response = openai_client.beta.threads.create()
        thread_id = thread_response.id
        vlog(f"Thread created with ID: {thread_id}")
        with open(f"Threads/{thread_id}.txt", "w") as file:
            file.write(thread_id)
        return thread_id
    except Exception as e:
        log(f"Failed to create thread: {e}", True)
        traceback.print_exc()  # This will print the stack trace to the log

def delete_thread(thread_id):
    vlog(f"Deleting thread with ID: {thread_id}...")
    try:
        openai_client.beta.threads.delete(thread_id)
        os.remove(f"Threads/{thread_id}.txt")
        log(f"Thread with ID: {thread_id} deleted successfully.")
    except Exception as e:
        log(f"Failed to delete thread: {e}", True)
        traceback.print_exc()





# === Command Actions === #

def stop_audio():
    sd.stop()
    play_feedback_sound('Sounds/Cancel.wav')
    log("Audio stopped.")

def cancel_command():
    log("Command cancelled.")
    play_feedback_sound('Sounds/Cancel.wav')

def shutdown():
    global shutdown_flag
    log("Force shutdown initiated.")
    play_feedback_sound('Sounds/Shutdown.wav', True)
    shutdown_flag = True


# Define a dictionary that maps specific commands to functions
command_actions = {
    "stop": stop_audio,
    "nevermind": cancel_command,
    "never mind": cancel_command,
    "cancel": cancel_command,
    "shutdown": shutdown,
    "shut down": shutdown,
}






# === Main Function === #

def main():
    log("Main program starting...")
    # Create a new thread for the conversation
    thread_id = create_thread()
    wake_word_thread = Thread(target=listen_for_wake_word)
    wake_word_thread.daemon = True
    wake_word_thread.start()

    try:
        log("Entering Main-Loop...\n")
        while not shutdown_flag:
            # Wait for the wake word to be detected
            speech_queue.get()
            command = recognize_speech()  # This line defines the 'command' variable
            if command:
                play_feedback_sound('Sounds/Heard.wav')
                response = process_command_with_assistant(thread_id, command)
                if response:  # Only synthesize and play speech if there's a response
                    audio_content = synthesize_speech(response)
                    play_speech(audio_content)
            speech_queue.task_done()
        log("Exiting Main-Loop...\n")
    except KeyboardInterrupt:
        log("Exiting program...")
    finally:
        if porcupine is not None:
            porcupine.delete()
        delete_thread(thread_id)  # Ensure the thread is deleted





# === Start Script === #

if __name__ == "__main__":
    try:
        # Ensure the Threads directory exists
        if not os.path.exists('Threads'):
            os.makedirs('Threads')
        calibrate_for_ambient_noise()
        main()
    except Exception as e:
        log(f"Unhandled exception in main: {e}", True)
        traceback.print_exc()