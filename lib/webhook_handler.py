import logging

import requests

module_logger = logging.getLogger('icad_cap_alerts.webhooks')


def post_to_webhook_ca(area_config, alert_json):
    webhook_url = area_config.get("webhook_url", None)
    webhook_headers = area_config.get("webhook_headers", None)
    if webhook_url:
        if webhook_headers:
            result = requests.post(webhook_url, headers=webhook_headers, json=alert_json)
        else:
            result = requests.post(webhook_url, json=alert_json)
        if result.status_code == 200:
            module_logger.info(f"Upload to {webhook_url} Successful!")
        else:
            module_logger.error(f"Upload to {webhook_url} failed. {result.status_code} {result.text}")
        return
    module_logger.warning(f"No Webhook URL, Skipping Webhook post.")
