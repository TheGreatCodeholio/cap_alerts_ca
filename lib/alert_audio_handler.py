import logging
import subprocess
import time

from lib.pulseaudio_thread_shared_state import pulseaudio_shared_state

module_logger = logging.getLogger("icad_cap_alerts.alert_audio_playback")


def play_mp3_on_sink(file_path, area_config):
    """
    Play an MP3 file on a specified PulseAudio sink.

    Args:
        file_path (str): Path to the MP3 file.
        area_config (dict): Configuration for the area, including area_id and sink name.
    """
    area_id = area_config.get("area_id")
    area_name = area_config.get("area_name")
    sink_name = area_config.get("alert_broadcast", {}).get("input_alert_audio_sink")

    if not sink_name or not area_id:
        module_logger.error("Sink name or area ID not provided.")
        return

    try:
        if wait_for_alert_inactive(area_id, max_wait_time=180):
            module_logger.info(f"Playing Alert Audio for {area_name}")
            play_audio(file_path, sink_name, area_id)
        else:
            module_logger.info("Max wait time exceeded, audio not played.")
    except Exception as e:
        module_logger.error(f"An error occurred: {e}")
        pulseaudio_shared_state.pa_shared[area_id]["alert_active"] = False


def wait_for_alert_inactive(area_id, max_wait_time=180):
    """
    Wait for the alert to become inactive.

    Args:
        area_id (str): The area ID to check for alert status.
        max_wait_time (int): Maximum time to wait in seconds.

    Returns:
        bool: True if the alert becomes inactive within the max wait time, False otherwise.
    """
    wait_time = 0
    while pulseaudio_shared_state.pa_shared[area_id]["alert_active"]:
        module_logger.debug("Waiting to play alert audio...")
        time.sleep(1)
        wait_time += 1
        if wait_time >= max_wait_time:
            return False
    return True


def play_audio(file_path, sink_name, area_id):
    """
    Play audio file on the specified PulseAudio sink.

    Args:
        file_path (str): Path to the audio file.
        sink_name (str): Name of the PulseAudio sink.
        area_id (str): The area ID.
    """
    module_logger.info(f"Playing Alert Audio on sink: {sink_name}")
    pulseaudio_shared_state.pa_shared[area_id]["alert_active"] = True
    command = f'mplayer -ao pulse::{sink_name} {file_path}'
    subprocess.run(command.split(), capture_output=True, text=True)
    pulseaudio_shared_state.pa_shared[area_id]["alert_active"] = False
