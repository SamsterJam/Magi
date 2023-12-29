import os
from openai import OpenAI
import speech_recognition as sr
from google.cloud import texttospeech
from scipy.io import wavfile
import sounddevice as sd
from dotenv import load_dotenv
import argparse

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Virtual Assistant')
parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
args = parser.parse_args()

# Global verbosity flag
verbose = True;

# Custom logging function
def log(message):
    if verbose:
        print(f"\033[90m{message}\033[0m")  # Gray text in terminal

# Load environment variables from a .env file
load_dotenv()

# Set up your API keys
google_credentials = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

# Initialize Conversation History
conversation_history = []

# Load in System Instructions
with open('system.txt', 'r') as file:
    systemContent = file.read()

conversation_history.append({"role": "system", "content": systemContent})

# Initialize the recognizer
recognizer = sr.Recognizer()

# Initialize Google Text-to-Speech client
tts_client = texttospeech.TextToSpeechClient.from_service_account_json(google_credentials)

# Function to recognize speech
def listen_for_speech():
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source)
        log("Listening...")
        audio = recognizer.listen(source)
        try:
            text = recognizer.recognize_google(audio)
            log(f"Recognized text: {text}")
            return text
        except sr.UnknownValueError:
            log("Could not understand audio")
        except sr.RequestError as e:
            log(f"Could not request results; {e}")
    return None

# Function to query OpenAI's GPT using the Conversation API
def ask_openai(question):
    # Add the user's message to the conversation history
    conversation_history.append({"role": "user", "content": question})
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo-1106",
            messages=conversation_history
        )
        # Extract the assistant's reply
        assistant_reply = response.choices[0].message.content  # Access the response using attributes
        log(f"OpenAI response: {assistant_reply}")
        
        # Add the assistant's reply to the conversation history
        conversation_history.append({"role": "assistant", "content": assistant_reply})
        
        return assistant_reply
    except Exception as e:  # Catch a more general exception
        log(f"Error querying OpenAI: {e}")
    return "I'm sorry, I can't process your request right now."


# Function to synthesize speech using Google TTS
def synthesize_speech(text):
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16
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
        filename = 'output.wav'
        with open(filename, 'wb') as out:
            out.write(audio_content)
        fs, data = wavfile.read(filename)
        log("Playing speech...")
        sd.play(data, fs)
        sd.wait()

# Main loop
wake_word = "hey bubba"
log("Virtual Assistant is running. Say 'Hey Bubba' to activate.")
while True:
    text = listen_for_speech()
    if text and wake_word in text.lower():
        log(f"You said: {text}")
        response = ask_openai(text)
        log(f"Assistant says: {response}")
        audio_content = synthesize_speech(response)
        play_speech(audio_content)