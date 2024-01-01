# === Imports === #

import os
import re
import datetime
import signal
import traceback
import time
import argparse
import numpy as np
import sounddevice as sd
from queue import Queue
import threading
from threading import Thread
from colorama import Fore, Style, init
import speech_recognition as sr
from google.cloud import texttospeech
from dotenv import load_dotenv
from openai import OpenAI
import pvporcupine
from scipy.io import wavfile
import json
import requests





# === Global Options === #

KEY_WORD = "Hey Magi"
CUSTOM_WAKE_WORD_FILE = "Magi-wake.ppn"

SPEAKING_RATE = 1.15
VOICE_NAME = "en-US-Polyglot-1"
PITCH = -5.0
OUTPUT_AUDIO_FILE = 'output.wav'

NOISE_CALIBRATION_TIME = 2
COMMAND_AWAIT_TIME_OUT = 10

SYSTEM_PROMPT_FILE = "system.txt"
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
wake_word_thread = None
shutdown_flag = False

vlog("Initialization Complete!")







# === Audio Manager === #

class AudioManager:
    def __init__(self):
        self.playback_queue = Queue()
        self.playback_thread = threading.Thread(target=self._playback_worker, daemon=True)
        self.playback_thread.start()
        self.playback_event = threading.Event()

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
                print(f"Error playing sound: {e}")
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


audio_manager = AudioManager()


def play_feedback_sound(sound_file, wait_full_sound=False):
    audio_manager.play_sound(sound_file, wait_full_sound)








# === Function Definitions === #

def calibrate_for_ambient_noise():
    global ambient_noise_energy_threshold
    with sr.Microphone() as source:
        log(f"Calibrating for ambient noise ({NOISE_CALIBRATION_TIME}s)... ")
        start_time = time.time()
        while time.time() - start_time < NOISE_CALIBRATION_TIME:
            if shutdown_flag:
                log("Calibration interrupted by shutdown.")
                return
            recognizer.adjust_for_ambient_noise(source, duration=1)
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
        while not shutdown_flag:  # Check the shutdown_flag
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


def process_command_with_assistant(thread_id, command, assistant_id):
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
        
        play_feedback_sound("Sounds/Request.wav")
        # Run the assistant on the thread
        vlog("OpenAI: Running Assistant with Thread...")
        run_response = openai_client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id  # Use the dynamic assistant ID passed to the function
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
            elif run_status.status == 'requires_action':
                # Handle the function call
                for tool_call in run_status.required_action.submit_tool_outputs.tool_calls:
                    if tool_call.function.name == "get_weather":
                        # Parse the JSON string into a Python object
                        arguments = json.loads(tool_call.function.arguments)
                        # Now you can access the location attribute
                        weather_info = get_weather(arguments["location"])
                        # Submit the result back to the assistant
                        openai_client.beta.threads.runs.submit_tool_outputs(
                            thread_id=thread_id,
                            run_id=run_response.id,
                            tool_outputs=[
                                {
                                    "tool_call_id": tool_call.id,
                                    "output": weather_info
                                }
                            ]
                        )
                continue
            time.sleep(1)  # Polling interval

        # Retrieve the assistant's messages
        vlog("OpenAI: Retrieving Response...")
        messages = openai_client.beta.threads.messages.list(
            thread_id=thread_id
        )
        vlog("OpenAI: Retrieved Response!")
        play_feedback_sound("Sounds/Received.wav")

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

        log(f"Assistant Response: {assistant_reply}")
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
        # Append the new thread ID to the active.treg file
        with open("active.treg", "a") as file:
            file.write(thread_id + "\n")
        return thread_id
    except Exception as e:
        log(f"Failed to create thread: {e}", True)
        traceback.print_exc()

def delete_thread(thread_id):
    vlog(f"Deleting thread with ID: {thread_id}...")
    try:
        openai_client.beta.threads.delete(thread_id)
        log(f"Thread with ID: {thread_id} deleted successfully.")
        # Remove the deleted thread ID from the active.treg file
        with open("active.treg", "r") as file:
            thread_ids = file.read().splitlines()
        if thread_id in thread_ids:
            thread_ids.remove(thread_id)
        with open("active.treg", "w") as file:
            file.write("\n".join(thread_ids) + "\n")
    except Exception as e:
        log(f"Failed to delete thread: {e}", True)
        traceback.print_exc()


def create_assistant():
    vlog("Creating a new assistant...")
    try:
        prompt = "You are an AI assistant. Please help the user with their queries."

        try:
            with open(SYSTEM_PROMPT_FILE, 'r') as file:
                prompt = file.read()
        except FileNotFoundError:
            log("System-Prompt file not found, using default!", True)


        # Define the assistant's instructions, model, and tools here
        assistant_response = openai_client.beta.assistants.create(
            name="Magi",
            instructions=prompt,
            tools=[
                {"type": "code_interpreter"},  # Add other tools/functions as needed
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get the current weather for a location",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "location": {"type": "string", "description": "The city to get the weather for"}
                            },
                            "required": ["location"]
                        }
                    }
                }
            ],
            model="gpt-3.5-turbo-1106"  # Replace with the desired model
        )
        assistant_id = assistant_response.id
        vlog(f"Assistant created with ID: {assistant_id}")
        # Append the new assistant ID to the active.areg file
        with open("active.areg", "a") as file:
            file.write(assistant_id + "\n")
        return assistant_id
    except Exception as e:
        log(f"Failed to create assistant: {e}", True)
        traceback.print_exc()


def delete_assistant(assistant_id):
    vlog(f"Deleting assistant with ID: {assistant_id}...")
    try:
        openai_client.beta.assistants.delete(assistant_id)
        log(f"Assistant with ID: {assistant_id} deleted successfully.")
        # Remove the deleted assistant ID from the active.areg file
        with open("active.areg", "r") as file:
            assistant_ids = file.read().splitlines()
        if assistant_id in assistant_ids:
            assistant_ids.remove(assistant_id)
        with open("active.areg", "w") as file:
            file.write("\n".join(assistant_ids) + "\n")
    except Exception as e:
        log(f"Failed to delete assistant: {e}", True)
        traceback.print_exc()



def signal_handler(sig, frame):
    global shutdown_flag, wake_word_thread, audio_manager
    log("Shutdown initiated by signal...")
    shutdown_flag = True
    if porcupine is not None:
        porcupine.delete()  # Stop Porcupine if it's running
    if wake_word_thread and wake_word_thread.is_alive():
        wake_word_thread.join()  # Ensure the wake word thread is joined
    audio_manager.shutdown()  # Shutdown the audio manager

def close_past_conversation_threads():
    vlog("Checking for unclosed conversation threads...")
    thread_ids = []
    try:
        with open("active.treg", "r") as file:
            thread_ids = file.read().splitlines()
    except FileNotFoundError:
        # If the file does not exist, create it
        with open("active.treg", "w") as file:
            pass

    if thread_ids:
        for thread_id in thread_ids:
            if thread_id:  # Ensure the thread ID is not empty
                delete_thread(thread_id)


def close_past_assistants():
    vlog("Checking for unclosed assistants...")
    assistant_ids = []
    try:
        with open("active.areg", "r") as file:
            assistant_ids = file.read().splitlines()
    except FileNotFoundError:
        # If the file does not exist, create it
        with open("active.areg", "w") as file:
            pass

    if assistant_ids:
        for assistant_id in assistant_ids:
            if assistant_id:  # Ensure the assistant ID is not empty
                delete_assistant(assistant_id)








# === Command Actions === #

def stop_audio():
    audio_manager.stop_all_sounds()
    play_feedback_sound('Sounds/Cancel.wav')
    log("Audio stopped.")

def cancel_command():
    log("Command cancelled.")
    play_feedback_sound('Sounds/Cancel.wav')

def shutdown():
    global shutdown_flag
    log("Shutdown initiated...")
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







# === Assistant Tool Functions === #

def get_weather(location):

    api_key = os.getenv("OPENWEATHERMAP_API_KEY")

    # Construct the API endpoint with the location and your API key
    url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}&units=imperial"
    
    try:
        # Make the API request
        response = requests.get(url)
        response.raise_for_status()  # Raise an HTTPError if the HTTP request returned an unsuccessful status code
        
       # Parse the JSON response
        weather_data = response.json()
        
        # Convert the JSON object to a string
        weather_data_string = json.dumps(weather_data)
        
        return weather_data_string
    
    except requests.RequestException as e:
        # Handle any errors that occur during the API request
        error_message = f"Failed to get weather data for {location}: {e}"
        print(error_message)
        return error_message







# === Main Function === #

def main():

    # Check if shutdown has been initiated before entering the main loop
    if shutdown_flag:
        log("Shutdown was initiated during startup. Skipping main loop.")
        return  # Exit the main function early

    vlog("Main program starting...")

    global wake_word_thread

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
                # Check if the command is a custom command
                if command.lower() in command_actions:
                    command_actions[command.lower()]()  # Execute the corresponding function
                else:
                    play_feedback_sound('Sounds/Heard.wav', True)
                    response = process_command_with_assistant(thread_id, command, assistant_id)
                    if response:  # Only synthesize and play speech if there's a response
                        audio_content = synthesize_speech(response)
                        play_speech(audio_content)
            speech_queue.task_done()
        log("Exiting Main-Loop...\n")
    except KeyboardInterrupt:
        log("Exiting program...")
    finally:
        wake_word_thread.join()
        if porcupine is not None:
            porcupine.delete()
        delete_thread(thread_id)  # Ensure the thread is deleted





# === Start Script === #

if __name__ == "__main__":
    try:
        # Register the signal handler for SIGINT
        signal.signal(signal.SIGINT, signal_handler)

        # Close any past conversation threads that were not properly closed
        close_past_conversation_threads()

        # Close any past assistants that were not properly closed
        close_past_assistants()

        # Create a new assistant
        assistant_id = create_assistant()

        # Calibrate for ambient noise
        calibrate_for_ambient_noise()

        # Start the main function
        main()

        # Delete the assistant when done
        delete_assistant(assistant_id)
    except Exception as e:
        log(f"Unhandled exception in main: {e}", True)
        traceback.print_exc()