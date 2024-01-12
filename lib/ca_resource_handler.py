import base64
import hashlib
import io
import logging
import os

from gtts import gTTS
import pydub

module_logger = logging.getLogger("icad_cap_alerts.canada_resource_handler")


def process_resources(resources, identifier, language, alert_folder_path, headline, description,
                      instruction):
    audio = 0
    image = 0
    if len(resources) >= 1:
        for resource in resources:
            if resource.get("mimeType", None) == "audio/mpeg":
                save_audio(resource, identifier, language, alert_folder_path)
                audio += 1

    if audio == 0:
        generate_tts_audio(identifier, language, alert_folder_path, headline, description, instruction)
        audio += 1

    return audio, image


def save_audio(resource, identifier, language, alert_folder_path):
    calculated_digest = hashlib.sha1(resource.get("derefUri", "").encode('utf-8')).hexdigest()
    if calculated_digest != resource.get('digest'):
        module_logger.warning("Digest for audio base64 doesn't match.")
        return

    audio_data = base64.b64decode(resource.get("derefUri", ""))
    with open(os.path.join(alert_folder_path, f"{identifier}_{language.split('-')[0]}.mp3"), 'wb') as file:
        file.write(audio_data)


def generate_tts_audio(identifier, language, alert_folder_path, headline, description, instruction):
    language = language.split("-")[0]
    alert_signal_file = os.path.join(os.getcwd(), 'var/audio_clips/ca_alert.mp3')
    if os.path.exists(os.path.join(os.getcwd(), 'var/audio_clips/ca_alert_alt.mp3')):
        alert_signal_file = os.path.join(os.getcwd(), 'var/audio_clips/ca_alert_alt.mp3')

    alert_audio_segment = pydub.AudioSegment.from_mp3(alert_signal_file)

    gtts_buf = io.BytesIO()
    tts = gTTS(f"{headline} ... {description} ... {instruction}", lang=language)

    tts.write_to_fp(gtts_buf)

    gtts_buf.seek(0)

    voice_audio_segment = pydub.AudioSegment.from_file(gtts_buf, format="mp3")

    alert_audio_full = alert_audio_segment + voice_audio_segment
    final_audio = normalize_audio(alert_audio_full)
    final_audio.export(os.path.join(alert_folder_path, f"{identifier}_{language}.mp3"))


def normalize_audio(audio_segment, target_dbfs=-20.0):
    """
    Normalize an audio file to a target dBFS.

    Args:
    file_path (str): Path to the audio file.
    target_dbfs (float): Target dBFS. Default is -20.0 dBFS.
    """

    # Calculate the difference between the target dBFS and the current dBFS
    change_in_dBFS = target_dbfs - audio_segment.dBFS

    # Apply the gain
    normalized_audio = audio_segment.apply_gain(change_in_dBFS)

    return normalized_audio