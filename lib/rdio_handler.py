import logging
import traceback

import requests

from lib.alert_audio_handler import convert_mp3_m4a

module_logger = logging.getLogger('icad_cap_alerts.rdio')


def upload_to_rdio_ca(mp3_path, area_config, alert_info_json):
    module_logger.info(f'Uploading To RDIO: {str(area_config["rdio"].get("api_url", ""))}')

    convert_result = convert_mp3_m4a(mp3_path)
    if not convert_result:
        return

    try:
        with open(mp3_path.replace(".mp3", ".m4a"), 'rb') as audio_file:
            data = {
                'key': area_config["rdio"].get("api_auth_token", ""),
                'dateTime': alert_info_json.get('sent'),
                'system': area_config["rdio"].get("system_id", 0),
                'talkgroup': area_config["rdio"].get("talkgroup_id", ""),
                'talkgroupGroup': 'Alerts',
                'talkgroupLabel': alert_info_json.get('sender_name'),
                'talkgroupTag': alert_info_json.get('sender_name'),
                'audio': (mp3_path.replace(".mp3", ".m4a").split('/')[-1], audio_file, 'audio/x-m4a'),

            }
            r = requests.post(area_config["rdio"].get("api_url", ""), files=data)
            module_logger.debug(f'{r.status_code}: {r.text}')
            r.raise_for_status()
    except FileNotFoundError as e:
        traceback.print_exc()
        module_logger.error(f'File not found: {str(e)}')
    except (requests.exceptions.RequestException, IOError) as e:
        module_logger.error(f'Failed Uploading To RDIO: {str(e)}')
    except Exception as e:
        traceback.print_exc()
        module_logger.error(f'Unexpected Error Uploading to RDIO: {e}')