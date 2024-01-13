import logging
import os
import subprocess
import time

from lib.pulseaudio_thread_shared_state import pulseaudio_shared_state

module_logger = logging.getLogger("icad_cap_alerts.alert_audio_playback")


def convert_mp3_m4a(mp3_file_path):
    if not os.path.isfile(mp3_file_path):
        module_logger.error(f"MP3 file does not exist: {mp3_file_path}")
        return f"MP3 file does not exist: {mp3_file_path}"

    module_logger.info(f'Converting MP3 to Mono M4A at 32k')

    command = f"ffmpeg -y -i {mp3_file_path} -af aresample=resampler=soxr -ar 22050 -c:a aac -ac 1 -b:a 32k {mp3_file_path.replace('.mp3', '.m4a')}"

    try:
        output = subprocess.check_output(command, shell=True, text=True, stderr=subprocess.STDOUT)
        module_logger.debug(output)
        module_logger.info(f"Successfully converted MP3 to M4A for file: {mp3_file_path.replace('.mp3', '.m4a')}")
    except subprocess.CalledProcessError as e:
        error_message = f"Failed to convert MP3 to M4A: {e.output}"
        module_logger.critical(error_message)
        return None
    except Exception as e:
        error_message = f"An unexpected error occurred during conversion: {str(e)}"
        module_logger.critical(error_message, exc_info=True)
        return None

    return True


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
    module_logger.info(f"Playing Alert Audio on sink: {sink_name}")
    command = ['mplayer', '-af', 'volume=10:1', f'-ao', f'pulse::{sink_name}', file_path]

    try:
        pulseaudio_shared_state.pa_shared[area_id]["alert_active"] = True
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        pulseaudio_shared_state.pa_shared[area_id]["alert_active"] = False

        # Log output on success
        module_logger.debug(f"mplayer output: {result.stdout}")
        return result.returncode

    except subprocess.CalledProcessError as e:
        # Log error details
        module_logger.error(f"mplayer failed: {e.stderr}, Return Code: {e.returncode}")
        return None
    except (OSError, ValueError) as e:
        module_logger.error(f"Error executing mplayer: {e}")
        return None
    finally:
        # Ensure the alert_active flag is reset even if an error occurs
        pulseaudio_shared_state.pa_shared[area_id]["alert_active"] = False