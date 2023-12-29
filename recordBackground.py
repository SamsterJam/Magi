import speech_recognition as sr

# Set the name of the output file
output_filename = "recorded_audio.wav"

# Initialize the recognizer
recognizer = sr.Recognizer()

# Callback function that saves the audio to a file when it's captured
def callback(recognizer, audio):
    try:
        # Save the audio to a WAV file
        with open(output_filename, "wb") as output_file:
            output_file.write(audio.get_wav_data())
        print(f"Audio recorded successfully and saved to {output_filename}")
    except Exception as e:
        print(f"Could not process the audio: {e}")

# Function to start listening in the background
def start_listening():
    # Create a microphone source and adjust for ambient noise
    with sr.Microphone() as source:
        print("Calibrating for Noise (2s)...")
        recognizer.adjust_for_ambient_noise(source, duration=2)
    # Now that we've adjusted for ambient noise, start listening in the background
    print("Listening...")
    stop_listening = recognizer.listen_in_background(sr.Microphone(), callback)
    return stop_listening

# Main function
def main():
    stop_listening = start_listening()

    try:
        while True:
            # Simulate doing other work in the main thread
            pass
    except KeyboardInterrupt:
        # Stop listening when the user presses Ctrl+C
        stop_listening(wait_for_stop=False)
        print("Stopped listening")

if __name__ == "__main__":
    main()