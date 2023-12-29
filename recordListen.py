import speech_recognition as sr

# Set the name of the output file
output_filename = "recorded_audio.wav"

# Initialize the recognizer
recognizer = sr.Recognizer()

# Function to record audio and save it to a file
def record_audio():
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source)
        print("Please speak into the microphone...")
        audio = recognizer.listen(source)

        # Save the audio to a WAV file
        with open(output_filename, "wb") as output_file:
            output_file.write(audio.get_wav_data())

        print(f"Audio recorded successfully and saved to {output_filename}")

# Main function
def main():
    record_audio()

if __name__ == "__main__":
    main()