from google.cloud import texttospeech
from utils import log, vlog, vvlog

class TextToSpeech:
    def __init__(self, config):
        self.config = config
        self.client = texttospeech.TextToSpeechClient.from_service_account_json(
            self.config.google_credentials
        )

    def synthesize_speech(self, text):
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name=self.config.voice_name
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            pitch=self.config.pitch,
            speaking_rate=self.config.speaking_rate
        )

        try:
            response = self.client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config
            )
            log("Speech synthesized successfully")
            return response.audio_content
        except Exception as e:
            log(f"Error synthesizing speech: {e}", error=True)
            return None