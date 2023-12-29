import os
import re
import datetime
from colorama import Fore, Style, init
import speech_recognition as sr
from google.cloud import texttospeech
from scipy.io import wavfile
import sounddevice as sd
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from a .env file
load_dotenv()

# Global options
KEY_WORD = "magi" # lowercase only
SPEAKING_RATE = 1.15
VOICE_NAME = "en-US-Polyglot-1"
PITCH = -5.0
SYSTEM_INSTRUCTIONS_FILE = 'system.txt'
OUTPUT_AUDIO_FILE = 'output.wav'

# Set up your API keys
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
GOOGLE_CREDENTIALS = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Initialize Google Text-to-Speech client
tts_client = texttospeech.TextToSpeechClient.from_service_account_json(GOOGLE_CREDENTIALS)

# Initialize colorama
init(autoreset=True)

# Initialize the recognizer
recognizer = sr.Recognizer()

# Initialize Conversation History
conversation_history = []

# Load in System Instructions
with open(SYSTEM_INSTRUCTIONS_FILE, 'r') as file:
    system_content = file.read()

conversation_history.append({"role": "system", "content": system_content})

# Custom logging function with timestamps and keyword highlighting
def log(message, highlight=False):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if highlight:
        # Use regular expressions for case-insensitive replacement
        message = re.sub(f'(?i){KEY_WORD}', f"{Fore.GREEN}{KEY_WORD.capitalize()}{Style.RESET_ALL}{Fore.LIGHTBLACK_EX}", message)
    print(f"{Fore.LIGHTBLACK_EX}[{timestamp}] {message}{Style.RESET_ALL}")

# Function to recognize speech with keyword highlighting
def listen_for_speech():
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source)
        log("Listening...")
        audio = recognizer.listen(source)
        try:
            text = recognizer.recognize_google(audio)
            # Use case-insensitive check for the keyword
            log(f"Recognizer heard: {text}", highlight=re.search(f'(?i){KEY_WORD}', text) is not None)
            return text
        except sr.UnknownValueError:
            log("Could not understand audio")
        except sr.RequestError as e:
            log(f"Could not request results; {e}")
    return None

# Function to query OpenAI's GPT using the Conversation API
def ask_openai(question):
    conversation_history.append({"role": "user", "content": question})
    try:
        response = client.chat.completions.create(
            model="gpt-4-1106-preview",
            messages=conversation_history
        )
        assistant_reply = response.choices[0].message.content
        conversation_history.append({"role": "assistant", "content": assistant_reply})
        return assistant_reply
    except Exception as e:
        log(f"Error querying OpenAI: {e}")
    return "I'm sorry, I can't process your request right now."

# Function to synthesize speech using Google TTS
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

# Function to play the synthesized speech
def play_speech(audio_content):
    if audio_content:
        with open(OUTPUT_AUDIO_FILE, 'wb') as out:
            out.write(audio_content)
        fs, data = wavfile.read(OUTPUT_AUDIO_FILE)
        log("Playing speech...")
        sd.play(data, fs)
        sd.wait()

# Main loop
def main():
    while True:
        text = listen_for_speech()
        if text:
            if KEY_WORD in text.lower():
                log(f"Keyword detected!")
                response = ask_openai(text)
                log(f"Assistant says: {response}")
                audio_content = synthesize_speech(response)
                play_speech(audio_content)
            else:
                log("Keyword not detected, waiting for the next command.")

if __name__ == "__main__":
    main()