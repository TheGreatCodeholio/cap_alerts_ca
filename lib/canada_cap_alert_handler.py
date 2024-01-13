import datetime
import json
import logging
import os
import time
import xml.etree.ElementTree as ET
from threading import Thread

import requests

from lib.alert_audio_handler import play_mp3_on_sink
from lib.ca_resource_handler import process_resources
from lib.mapping_handler import create_map_image
from lib.rdio_handler import upload_to_rdio_ca
from lib.sqlite_handler import SQLiteDatabase
from lib.webhook_handler import post_to_webhook_ca

module_logger = logging.getLogger('icad_cap_alerts.canada_cap_alerts')
alert_path = os.path.join(os.getcwd(), "static/alerts")


def process_alert(db, config_data, xml_data):
    """Parse the CAP alert XML data."""
    root = ET.fromstring(xml_data)

    namespaces = config_data["canada_cap_stream"].get("namespaces", {"cap": "urn:oasis:names:tc:emergency:cap:1.2"})

    # Parse the main elements of the CAP message
    identifier = root.find('cap:identifier', namespaces).text
    sender = root.find('cap:sender', namespaces).text
    timestamp = root.find('cap:sent', namespaces).text
    status = root.find('cap:status', namespaces).text
    msgType = root.find('cap:msgType', namespaces).text
    scope = root.find('cap:scope', namespaces).text

    urldate, _, _ = timestamp.partition('T')
    reference = timestamp + "I" + identifier
    filename = reference.translate({ord('-'): ord('_'), ord(':'): ord('_'), ord('+'): ord('p')})

    # Print the parsed data (or process it as needed)
    print(f"Identifier: {identifier}")
    print(f"Sender: {sender}")
    print(f"Sent: {timestamp}")
    print(f"Status: {status}")
    print(f"Message Type: {msgType}")
    print(f"Scope: {scope}")

    alert_folder_path = os.path.join(alert_path, filename)
    if not os.path.exists(alert_folder_path):
        os.makedirs(alert_folder_path)

    xml_data = fetch_archive_xml(config_data, identifier, urldate, filename, alert_folder_path)
    alert_json = convert_alert_xml(config_data, filename, xml_data, alert_folder_path)

    polygons = []
    for area in alert_json.get("en-CA", {}).get("areas", {}):
        for co in area.get("polygon"):
            polygons.append(co)
    map_base64 = create_map_image(config_data, filename, polygons, alert_folder_path)
    alert_json["map_image"] = map_base64
    alert_json["map_url"] = f'{config_data["general"].get("baseurl")}/static/alerts/{filename}/{filename}_map.png'

    ## Process Resources in XML or Generate TTS:
    for x in alert_json:
        if "-CA" in x:
            audio, image = process_resources(alert_json[x].get("resources"), identifier, x, alert_folder_path,
                                             alert_json[x].get("headline"), alert_json[x].get("description"),
                                             alert_json[x].get("area_list", []))
            # add a short delay to make sure audio file created before sending alert
            time.sleep(15)
            if audio >= 1:
                alert_json[x][
                    "mp3_url"] = f'{config_data["general"].get("baseurl")}/static/alerts/{identifier}/{identifier}_{x.split("-")[0]}.mp3'
                alert_json[x]["mp3_local_path"] = os.path.join(alert_folder_path, f"{identifier}_{x.split('-')[0]}.mp3")

            dispatch_alerts(config_data["canada_cap_stream"].get("alert_areas", []), alert_folder_path, identifier,
                            alert_json[x], alert_json)

    db_result = insert_alert_data(db, alert_json)
    if not db_result.get("success"):
        module_logger.error(db_result.get("message"))
        return
    #
    # post_to_webhook(config_data.get("webhook_url"), alert_json)


def fetch_archive_xml(config_data, identifier, urldate, filename, alert_folder_path):
    retries = 0
    module_logger.info(f"Fetching alert XML for: {identifier}")
    while retries < config_data["canada_cap_stream"].get("max_fetch_retries", 3):
        for host in config_data["canada_cap_stream"].get("archive_hosts", ["http://capcp1.naad-adna.pelmorex.com",
                                                                           "http://capcp2.naad-adna.pelmorex.com"]):
            url = f"{host}/{urldate}/{filename}.xml"
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.103 Safari/537.36'}
                response = requests.get(url, headers=headers)

                if response.status_code == 200:
                    xml_data = response.content

                    if config_data["canada_cap_stream"].get("save_xml", 0) == 1:
                        alert_file_path = os.path.join(alert_folder_path, f"{filename}.xml")
                        with open(alert_file_path, 'wb') as f:
                            f.write(xml_data)

                    return xml_data

            except requests.ConnectionError:
                module_logger.error(f"Connection error occurred while fetching the alert {identifier}")
                return None

            except Exception as e:
                module_logger.error(f"An error occurred while fetching the alert {identifier}: {e}")
                return None

        # Retry logic
        retries += 1
        if retries < config_data["canada_cap_stream"].get("max_fetch_retries", 3):
            module_logger.warning(
                f"Retrying... Attempt {retries} of {config_data['canada_cap_stream'].get('max_fetch_retries', 3)}")
            time.sleep(config_data["canada_cap_stream"].get("retry_delay", 5))

    module_logger.error(f"Error fetching alert {identifier}")
    return None


def convert_alert_xml(config_data, filename, xml_data, alert_folder_path):
    # Define the namespace
    namespace = {'ns': 'urn:oasis:names:tc:emergency:cap:1.2'}

    # Parse the XML
    root = ET.fromstring(xml_data)

    # Function to extract text from an element
    def get_text(element, default=''):
        return element.text.strip() if element is not None and element.text is not None else default

    # Construct the dictionary
    alert_dict = {
        "namespace": root.tag[root.tag.find('}') + 1:],  # Extract namespace after '}' character
        "identifier": get_text(root.find('ns:identifier', namespace)),
        "sender": get_text(root.find('ns:sender', namespace)),
        "sent": get_text(root.find('ns:sent', namespace)),
        "status": get_text(root.find('ns:status', namespace)),
        "msgType": get_text(root.find('ns:msgType', namespace)),
        "source": get_text(root.find('ns:source', namespace)),
        "scope": get_text(root.find('ns:scope', namespace)),
        "codes": [get_text(code) for code in root.findall('ns:code', namespace)],
        "note": get_text(root.find('ns:note', namespace)),
        "references": get_text(root.find('ns:references', namespace), default='').split()

    }

    # Process each 'info' section
    for info in root.findall('ns:info', namespace):
        language = get_text(info.find('ns:language', namespace))

        # Construct the language-specific details
        alert_dict[language] = {
            "language": language.split('-')[0],
            "category": get_text(info.find('ns:category', namespace)),
            "event": get_text(info.find('ns:event', namespace)),
            "responseType": get_text(info.find('ns:responseType', namespace)),
            "urgency": get_text(info.find('ns:urgency', namespace)),
            "severity": get_text(info.find('ns:severity', namespace)),
            "certainty": get_text(info.find('ns:certainty', namespace)),
            "audience": get_text(info.find('ns:audience', namespace)),
            "eventCodes": {get_text(ec.find('ns:valueName', namespace)): get_text(ec.find('ns:value', namespace)) for ec
                           in
                           info.findall('ns:eventCode', namespace)},
            "sent": get_text(root.find('ns:sent', namespace)),
            "effective": get_text(info.find('ns:effective', namespace)),
            "expires": get_text(info.find('ns:expires', namespace)),
            "sender_name": get_text(info.find('ns:senderName', namespace)),
            "headline": get_text(info.find('ns:headline', namespace)),
            "description": get_text(info.find('ns:description', namespace)),
            "instruction": get_text(info.find('ns:instruction', namespace)),
            "web": get_text(info.find('ns:web', namespace)),
            "parameters": {get_text(p.find('ns:valueName', namespace)): get_text(p.find('ns:value', namespace)) for p in
                           info.findall('ns:parameter', namespace)},
            "areas": [],
            "resources": [],
            "sgc_codes": [],
            "mp3_local_path": "",
            "mp3_url": "",
            "mp3_duration": 0
        }

        for res in info.findall('ns:resource', namespace):
            resource_dict = {
                "resourceDesc": get_text(res.find('ns:resourceDesc', namespace), default=""),
                "mimeType": get_text(res.find('ns:mimeType', namespace), default=""),
                "size": get_text(res.find('ns:size', namespace), default=""),
                "uri": get_text(res.find('ns:uri', namespace), default=""),
                "derefUri": get_text(res.find('ns:derefUri', namespace), default=""),
                "digest": get_text(res.find('ns:digest', namespace), default="")
            }

            alert_dict[language]["resources"].append(resource_dict)

        area_text = []

        for area in info.findall('ns:area', namespace):  # Loop through each area in your data
            area_dict = {
                "areaDesc": get_text(area.find('ns:areaDesc', namespace)),
                "polygon": [get_text(polygon) for polygon in area.findall('ns:polygon', namespace)],
                "geocodes": {}
            }
            area_text.append(get_text(area.find('ns:areaDesc', namespace)))
            for gc in area.findall('ns:geocode', namespace):
                code_type = get_text(gc.find('ns:valueName', namespace))
                code_value = get_text(gc.find('ns:value', namespace))
                area_dict["geocodes"][code_type] = code_value
                if code_type.startswith("profile:CAP-CP:Location"):
                    alert_dict[language]["sgc_codes"].append(int(code_value))

            alert_dict[language]["areas"].append(area_dict)
            alert_dict[language]["area_list"] = area_text

    if config_data["canada_cap_stream"].get("save_json", 0) == 1:
        alert_file_path = os.path.join(alert_folder_path, f"{filename}.json")
        with open(alert_file_path, 'w') as f:
            json.dump(alert_dict, f, indent=4)

    return alert_dict


def dispatch_alerts(area_config, alert_folder_path, identifier, info_json, alert_json_full):
    module_logger.debug("Starting Dispatch")
    for area in area_config:
        if area.get("language", "en") == info_json.get("language"):
            prov_codes = [str(code) for code in area["sgc_codes"] if len(str(code)) == 2]
            cd_codes = [str(code) for code in area["sgc_codes"] if len(str(code)) == 4]
            csd_codes = [str(code) for code in area["sgc_codes"] if len(str(code)) == 7]
            module_logger.debug(prov_codes)
            module_logger.debug(cd_codes)
            module_logger.debug(csd_codes)

            alert_sgc_codes = [str(code) for code in info_json.get("sgc_codes", [])]

            module_logger.debug(alert_sgc_codes)

            filter_match = False

            for sgc_code in alert_sgc_codes:
                if sgc_code[:2] in prov_codes or sgc_code[:4] in cd_codes or sgc_code[:7] in csd_codes:
                    filter_match = True
                    module_logger.info("SGC Match Found")
                    break

            if filter_match:
                Thread(target=post_to_webhook_ca, args=(area, alert_json_full)).start()
                if info_json.get("mp3_local_path") and area.get("alert_broadcast", {}).get("enabled", 0) == 1:
                    mp3_path = os.path.join(alert_folder_path, f"{identifier}_{info_json.get('language')}.mp3")
                    Thread(target=play_mp3_on_sink, args=(mp3_path, area)).start()
                if area.get("rdio", {}).get("enabled", 0) == 1:
                    mp3_path = os.path.join(alert_folder_path, f"{identifier}_{info_json.get('language')}.mp3")
                    Thread(target=upload_to_rdio_ca, args=(mp3_path, area, info_json)).start()


def to_epoch(date_str):
    """Convert ISO 8601 date strings to epoch time."""
    if date_str:
        # Assuming the date string is in ISO 8601 format like '2024-01-07T01:31:08-00:00'
        # Adjust the format if your input varies
        fmt = "%Y-%m-%dT%H:%M:%S%z"
        dt = datetime.datetime.strptime(date_str, fmt)
        return int(dt.timestamp())
    return None


def get_alerts(database: SQLiteDatabase, identifier=None, geocode=None, active_only=False):
    # Step 1: Query the ca_alerts table
    alerts = query_alerts(database, identifier, geocode, active_only)

    # Step 2: For each alert, query the ca_alert_info table
    for alert in alerts:
        alert['info'] = query_alert_info(database, alert['id'])

        # Step 3: For each info, query the ca_alert_areas table
        for info in alert['info']:
            info['areas'] = query_alert_areas(database, info['id'])

            # Step 4: For each area, query the ca_alert_geocodes table
            for area in info['areas']:
                area['geocodes'] = query_alert_geocodes(database, area['id'])

    return alerts


def query_alerts(database, identifier, geocode, active_only):
    where_clauses = []
    params = []

    if identifier:
        where_clauses.append("a.identifier = ?")
        params.append(identifier)

    if geocode:
        if not isinstance(geocode, list):
            geocode = [geocode]
        placeholders = ','.join('?' for _ in geocode)
        where_clauses.append(f"g.geocode_value IN ({placeholders})")
        params.extend(geocode)

    if active_only:
        where_clauses.append("a.is_active > ?")
        params.append(1)

    where_clause = " AND ".join(where_clauses) if where_clauses else "1"

    query = f"""
        SELECT DISTINCT a.*
        FROM ca_alerts a
        LEFT JOIN ca_alert_info i ON a.id = i.alert_id
        LEFT JOIN ca_alert_areas ar ON i.id = ar.info_id
        LEFT JOIN ca_alert_geocodes g ON ar.id = g.area_id
        WHERE {where_clause}
        """
    result = database.execute_query(query, params)
    return result['result']


def query_alert_info(database, alert_id):
    query = "SELECT * FROM ca_alert_info WHERE alert_id = ?"
    result = database.execute_query(query, (alert_id,))
    return result['result']


def query_alert_areas(database, info_id):
    query = "SELECT * FROM ca_alert_areas WHERE info_id = ?"
    result = database.execute_query(query, (info_id,))
    return result['result']


def query_alert_geocodes(database, area_id):
    query = "SELECT * FROM ca_alert_geocodes WHERE area_id = ?"
    result = database.execute_query(query, (area_id,))
    return {row['geocode_key']: row['geocode_value'] for row in result['result']}


def insert_alert_data(database: SQLiteDatabase, alert_data: dict):
    # Convert 'sent' field to epoch
    sent_epoch = to_epoch(alert_data.get('sent'))

    # Insert into the ca_alerts table
    alert_insert_query = """
    INSERT INTO ca_alerts (namespace, identifier, sender, sent, status, msgType, source, scope, note, map_file, is_active, parent_alert_id)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    alert_params = (
        alert_data.get('namespace'),
        alert_data.get('identifier'),
        alert_data.get('sender'),
        sent_epoch,  # Use the converted epoch time
        alert_data.get('status'),
        alert_data.get('msgType'),
        alert_data.get('source'),
        alert_data.get('scope'),
        alert_data.get('note'),
        alert_data.get('map_file'),
        1,
        None
    )
    alert_result = database.execute_commit(alert_insert_query, alert_params, return_row=True)
    if not alert_result['success']:
        return alert_result  # Return early if the insert failed

    alert_id = alert_result['row_id']

    references = alert_data.get("references", [])
    identifiers = [identifier.split(",")[1] for identifier in references]

    for i in identifiers:
        ref_query = "INSERT INTO ca_alert_references (parent_alert_id, identifier_reference) VALUES (?, ?)"
        ref_params = (alert_id, i)
        database.execute_commit(ref_query, ref_params)

        update_old_query = "UPDATE ca_alerts SET is_active = ?, parent_alert_id = ? WHERE identifier = ?"
        update_old_params = (0, alert_id, i)
        database.execute_commit(update_old_query, update_old_params)

    # Process each language section in the alert data
    for lang, info in alert_data.items():
        # Skip if the value is not a dictionary (e.g., 'sent' field)
        if not isinstance(info, dict):
            continue

        effective_epoch = to_epoch(info.get('effective'))
        expires_epoch = to_epoch(info.get('expires'))

        info_insert_query = """
        INSERT INTO ca_alert_info (alert_id, language, category, event, responseType, urgency, severity, certainty, audience, effective, expires, sender_name, headline, description, instruction, web, audio_url, image_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ? ,?)
        """
        info_params = (
            alert_id,
            lang,
            info.get('category'),
            info.get('event'),
            info.get('responseType'),
            info.get('urgency'),
            info.get('severity'),
            info.get('certainty'),
            info.get('audience'),
            effective_epoch,  # Use the converted epoch time
            expires_epoch,  # Use the converted epoch time
            info.get('sender_name'),
            info.get('headline'),
            info.get('description'),
            info.get('instruction'),
            info.get('web'),
            info.get('audio_url'),
            info.get('image_url')
        )
        info_result = database.execute_commit(info_insert_query, info_params, return_row=True)
        if not info_result['success']:
            return info_result  # Return early if the insert failed

        info_id = info_result['row_id']

        # Insert into the ca_alert_areas table for each area
        for area in info.get('areas', []):
            area_insert_query = """
            INSERT INTO ca_alert_areas (info_id, alert_id, areaDesc, polygon)
            VALUES (?, ?, ?, ?)
            """
            area_params = (
                info_id,
                alert_id,
                area.get('areaDesc'),
                ' '.join(area.get('polygon', []))  # Convert list of coordinates to space-separated string
            )
            area_result = database.execute_commit(area_insert_query, area_params, return_row=True)
            if not area_result['success']:
                return area_result  # Return early if the insert failed

            area_id = area_result['row_id']  # Get the ID of the newly inserted area

            # Insert into the ca_alert_geocodes table for each geocode
            for geocode_key, geocode_value in area.get('geocodes', {}).items():
                geocode_insert_query = """
                INSERT INTO ca_alert_geocodes (alert_id, area_id, geocode_key, geocode_value)
                VALUES (?, ?, ?, ?)
                """
                geocode_params = (alert_id, area_id, geocode_key, geocode_value)
                geocode_result = database.execute_commit(geocode_insert_query, geocode_params)
                if not geocode_result['success']:
                    return geocode_result  # Return early if the insert failed

    return {'success': True, 'message': 'Alert data inserted successfully'}
