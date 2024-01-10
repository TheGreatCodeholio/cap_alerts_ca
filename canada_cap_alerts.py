import base64
import io
import json
import os
import socket
import xml.etree.ElementTree as ET

import time
import requests
import argparse
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
from cartopy.io.img_tiles import OSM
from cartopy.io.img_tiles import GoogleTiles

########################################################################################################################
HOSTS = ["streaming1.naad-adna.pelmorex.com", "streaming2.naad-adna.pelmorex.com"]
PORT = 8080
HEARTBEAT_INTERVAL = 60
MAX_HEARTBEAT_DELAY = 120
BUFFER_SIZE = 1024  # Adjust as needed
RECONNECT_DELAY = 5  # Seconds to wait before trying to reconnect
NAMESPACES = {'cap': 'urn:oasis:names:tc:emergency:cap:1.2'}
DATA_DIR = os.getcwd()
ARCHIVE_HOSTS = ["http://capcp1.naad-adna.pelmorex.com", "http://capcp2.naad-adna.pelmorex.com"]
MAX_RETRIES = 3
RETRY_DELAY = 30

########################################################################################################################

map_image_base64 = None


def get_command_line_args():
    parser = argparse.ArgumentParser(description="Canada Alert CAP")
    parser.add_argument('-a', '--alert_test', type=str, default=None, help="Path to Test Alert XML")
    return parser.parse_args()


def connect_to_stream(host, port):
    try:
        # Create a socket object
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Connect to the server
        s.connect((host, port))
        print(f"Connected to {host}")
        return s
    except socket.error as e:
        print(f"Error connecting to {host}: {e}")
        return None


def post_to_webhook(webhook_url, post_json):
    if webhook_url:
        result = requests.post(webhook_url, json=post_json)
        if result.status_code == 200:
            print(f"Upload to {webhook_url} Successful!")
        else:
            print(f"Upload to {webhook_url} failed. {result.status_code} {result.text}")
        return
    print(f"No Webhook URL, Skipping Webhook post.")


def fetch_reference(identifier, urldate, filename, archive_alert):
    retries = 0
    while retries < MAX_RETRIES:
        for host in ARCHIVE_HOSTS:
            url = f"{host}/{urldate}/{filename}.xml"
            try:
                print(f"Fetching alert {identifier} using URL {url}")
                headers = {
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.103 Safari/537.36'}
                response = requests.get(url, headers=headers)

                if response.status_code == 200:
                    xml_data = response.content

                    if archive_alert:
                        alert_path = os.path.join(DATA_DIR, "alerts")
                        if not os.path.exists(alert_path):
                            os.makedirs(alert_path)

                        alert_file_path = os.path.join(alert_path, f"{filename}.xml")
                        with open(alert_file_path, 'wb') as f:
                            f.write(xml_data)

                    return xml_data

            except requests.ConnectionError:
                print(f"Connection error occurred while fetching the alert {identifier}")
                return None

            except Exception as e:
                print(f"An error occurred while fetching the alert {identifier}: {e}")
                return None

        # Retry logic
        retries += 1
        if retries < MAX_RETRIES:
            print(f"Retrying... Attempt {retries} of {MAX_RETRIES}")
            time.sleep(RETRY_DELAY)

    print(f"Error fetching alert {identifier}")
    return None


def convert_alert_xml(xml_data):
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
        "references": get_text(root.find('ns:references', namespace), default='').split(),
    }

    # Process each 'info' section
    for info in root.findall('ns:info', namespace):
        language = get_text(info.find('ns:language', namespace))

        # Construct the language-specific details
        alert_dict[language] = {
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
            "effective": get_text(info.find('ns:effective', namespace)),
            "expires": get_text(info.find('ns:expires', namespace)),
            "sender_name": get_text(info.find('ns:senderName', namespace)),
            "headline": get_text(info.find('ns:headline', namespace)),
            "description": get_text(info.find('ns:description', namespace)),
            "instruction": get_text(info.find('ns:instruction', namespace)),
            "web": get_text(info.find('ns:web', namespace)),
            "parameters": {get_text(p.find('ns:valueName', namespace)): get_text(p.find('ns:value', namespace)) for p in
                           info.findall('ns:parameter', namespace)},
            "areas": []
        }
        for area in info.findall('ns:area', namespace):  # Loop through each area in your data
            area_dict = {
                "areaDesc": get_text(area.find('ns:areaDesc', namespace)),
                "polygon": [get_text(polygon) for polygon in area.findall('ns:polygon', namespace)],
                "geocodes": {get_text(gc.find('ns:valueName', namespace)): get_text(gc.find('ns:value', namespace)) for
                             gc in
                             area.findall('ns:geocode', namespace)}
            }
            alert_dict[language]["areas"].append(area_dict)
    print(alert_dict)
    return alert_dict


def create_map_image(alert_file_name, polygons, alert_description, save_image):
    desired_width_px = 800  # Desired width in pixels
    desired_height_px = 800  # Desired height in pixels
    dpi = 300

    # Calculate the size in inches
    width_in = desired_width_px / dpi
    height_in = desired_height_px / dpi

    # Initialize min and max values with the first point
    first_point = polygons[0].split()[0]
    min_lat, max_lon = map(float, first_point.split(','))
    max_lat, min_lon = min_lat, max_lon

    # Iterate through each polygon and each point to find the min and max values
    for polygon in polygons:
        points = polygon.split()
        for point in points:
            lat, lon = map(float, point.split(','))
            min_lat = min(min_lat, lat)
            max_lat = max(max_lat, lat)
            min_lon = min(min_lon, lon)
            max_lon = max(max_lon, lon)

    # Create a plot with a specific projection
    fig, ax = plt.subplots(figsize=(width_in, height_in), subplot_kw={'projection': ccrs.PlateCarree()})
    #tiles = OSM()
    tiles = GoogleTiles()
    ax.add_image(tiles, 7)

    # Minimum ranges for latitude and longitude
    min_lat_range = 5  # Adjust as needed
    min_lon_range = 5  # Adjust as needed

    # Calculate ranges
    lat_range = max(max_lat - min_lat, min_lat_range)
    lon_range = max(max_lon - min_lon, min_lon_range)

    # Calculate the center of the bounding box
    center_lat = (max_lat + min_lat) / 2
    center_lon = (max_lon + min_lon) / 2

    # Set the extent with minimum ranges
    ax.set_extent([center_lon - lon_range / 2, center_lon + lon_range / 2, center_lat - lat_range / 2,
                   center_lat + lat_range / 2])

    # Plot each polygon
    for polygon in polygons:
        plot_polygon(ax, polygon, line_width=0.3, alpha=0.3)

    #ax.set_title(alert_description.title())

    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    alerts_path = os.path.join(DATA_DIR, "alerts")

    if not os.path.exists(alerts_path):
        os.makedirs(alerts_path)

    alert_file_name = f"{alert_file_name}_map.png"

    plt.savefig(os.path.join(alerts_path, alert_file_name), dpi=dpi, bbox_inches='tight', pad_inches=0)
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=dpi, bbox_inches='tight', pad_inches=0)
    buf.seek(0)
    image_base64 = base64.b64encode(buf.read()).decode('utf-8')
    return image_base64


def plot_polygon(ax, polygon, line_width=0.5, fill_color='red', alpha=0.5):
    # Split the string into pairs of lat, lon and reverse the order
    points = polygon.split(' ')
    lats, lons = zip(*[map(float, point.split(',')) for point in points[::-1]])  # Note the [::-1] to reverse

    # Plot the polygon outline
    ax.plot(lons, lats, marker='o', color=fill_color, markersize=1, linestyle='-', linewidth=line_width, transform=ccrs.Geodetic())

    # Fill the polygon with the specified color and transparency
    ax.fill(lons, lats, color=fill_color, alpha=alpha, transform=ccrs.Geodetic())


def process_alert(config_data, xml_data, test_mode=False):
    """Parse the CAP alert XML data."""
    root = ET.fromstring(xml_data)

    # Parse the main elements of the CAP message
    identifier = root.find('cap:identifier', NAMESPACES).text
    sender = root.find('cap:sender', NAMESPACES).text
    timestamp = root.find('cap:sent', NAMESPACES).text
    status = root.find('cap:status', NAMESPACES).text
    msgType = root.find('cap:msgType', NAMESPACES).text
    scope = root.find('cap:scope', NAMESPACES).text

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

    xml_data = fetch_reference(identifier, urldate, filename, True if not test_mode else False)
    alert_json = convert_alert_xml(xml_data)
    polygons = []
    for area in alert_json.get("en-CA", {}).get("areas", {}):
        for co in area.get("polygon"):
            polygons.append(co)
    map_base64 = create_map_image(filename, polygons, alert_json.get("en-CA", {}).get("headline"), True)
    alert_json["map_image"] = map_base64

    post_to_webhook(config_data.get("webhook_url"), alert_json)


def stream_xml(config_data, hosts, port):
    while True:
        for host in hosts:
            sock = connect_to_stream(host, port)
            if sock:
                try:
                    buffer = b''
                    last_heartbeat = time.time()  # Record the time when the last heartbeat was received

                    while True:
                        # Receive data from the stream
                        data = sock.recv(BUFFER_SIZE)
                        if not data:
                            break

                        # Decode and add to buffer
                        buffer += data

                        # Check for the end of an alert or heartbeat message
                        if b'</alert>' in buffer:
                            try:
                                alert_text = buffer.decode('utf-8')
                                if 'NAADS-Heartbeat' in alert_text:
                                    # Process heartbeat
                                    print("Heartbeat received")
                                    last_heartbeat = time.time()  # Update the last heartbeat time
                                else:
                                    # Process a regular alert
                                    process_alert(config_data, alert_text)
                            except UnicodeDecodeError as e:
                                print(f"Error decoding alert: {e}")

                            buffer = b''  # Reset the BUffer

                        # Check if the heartbeat delay has been exceeded
                        if time.time() - last_heartbeat > MAX_HEARTBEAT_DELAY:
                            print("Heartbeat delay exceeded, reconnecting...")
                            break

                except socket.error as e:
                    print(f"Error receiving data: {e}")
                finally:
                    sock.close()
                    print(f"Disconnected from {host}")

        print(f"Attempting to reconnect in {RECONNECT_DELAY} seconds...")
        time.sleep(RECONNECT_DELAY)


def load_configuration():
    config_path = os.path.join(DATA_DIR, "etc")
    config_file = "config.json"
    if os.path.exists(os.path.join(config_path, config_file)):
        with open(os.path.join(config_path, config_file), 'r') as cf:
            config_data = json.loads(cf.read())
        return config_data
    else:
        print("Please create a config file in etc/config.json")
        return False


def main():
    """Main function to stream and parse CAP XML data."""
    args = get_command_line_args()
    config_data = load_configuration()
    if not config_data:
        exit(1)
    if args.alert_test:
        xml_path = args.alert_test
        if not os.path.exists(xml_path):
            print("Can not find specified Test Alert XML file.")

        with open(xml_path, "r") as xml_file:
            xml_data = xml_file.read()

        process_alert(config_data, xml_data, True)

    else:
        stream_xml(config_data, HOSTS, PORT)


if __name__ == "__main__":
    main()
