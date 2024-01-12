import json
import os

default_config = {
    "log_level": 1,
    "general": {
        "test_mode": True,
        "base_url": "http://localhost",
        "cookie_domain": "localhost",
        "cookie_secure": False,
        "cookie_name": "icad_cap_alerts",
        "cookie_path": "/"
    },
    "canada_cap_stream": {
        "enabled": 1,
        "save_xml": 1,
        "save_map": 1,
        "save_json": 0,
        "hosts": ["streaming1.naad-adna.pelmorex.com", "streaming2.naad-adna.pelmorex.com"],
        "port": 8080,
        "heartbeat_interval": 60,
        "max_heartbeat_delay": 120,
        "reconnect_delay": 5,
        "max_reconnect_retries": 3,
        "namespaces": {"cap": "urn:oasis:names:tc:emergency:cap:1.2"},
        "archive_hosts": ["http://capcp1.naad-adna.pelmorex.com", "http://capcp2.naad-adna.pelmorex.com"],
        "alert_areas": [
            {
                "area_id": 1,
                "area_name": "Canada Wide",
                "sgc_codes": [10, 11, 12, 13, 24, 35, 46, 47, 48, 59, 60, 61],
                "webhook_url": "",
                "webhook_headers": "",
                "rdio": {
                    "enabled": 0,
                    "api_url": "https://example.com/api/call-upload",
                    "api_auth_token": "3e6701bf-1c1f-4dfd-b28c-117759d4203c",
                    "system_id": 234,
                    "talkgroup_id": 999
                },
                "alert_broadcast": {
                    "enabled": 0,
                    "input_alert_audio_sink": "ca_alert_in",
                    "input_stream_audio_sink": "ca_broadcast_in",
                    "output_audio_sink": "ca_audio_out",
                    "icecast": {
                        "bitrate": 16,
                        "host": "",
                        "port": 7778,
                        "mount": "",
                        "password": "",
                        "stream_name": "",
                        "description": ""
                    }
                }
            }
        ]
    },
    "sqlite": {
        "database_path": "icad_cap_warn.db"
    }
}


def save_config(config_path, config_data=False):
    if not os.path.exists(config_path):
        os.makedirs(config_path)

    with open(os.path.join(config_path, "config.json"), "w") as outfile:
        if not config_data:
            outfile.write(json.dumps(default_config, indent=4))
        else:
            outfile.write(json.dumps(config_data, indent=4))
