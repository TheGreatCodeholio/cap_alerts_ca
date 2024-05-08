import json
import os
import threading
import time
import traceback
from functools import wraps

from flask import Flask, request, session, redirect, url_for, render_template, flash, jsonify

from lib.audio_relay_handler import AudioRelay
from lib.canada_cap_alert_handler import get_alerts, process_alert
from lib.canada_cap_stream_handler import canada_cap_stream
from lib.config_handler import save_config
from lib.icecast_handler import IcecastStreamer
from lib.logging_handler import CustomLogger
from lib.sqlite_handler import SQLiteDatabase

from lib.ca_cap_thread_shared_state import ca_cap_shared_state
from lib.user_handler import authenticate_user

app_name = "icad_cap_alerts"
config_data = {}
root_path = os.getcwd()
config_file = 'config.json'
log_path = os.path.join(root_path, 'log')
log_file_name = f"{app_name}.log"
config_path = os.path.join(root_path, "etc")
alert_data_path = os.path.join(root_path, "static/alerts")
audio_path = os.path.join(root_path, "static/audio")

active_threads = []

if not os.path.exists(config_path):
    os.makedirs(config_path)

if not os.path.exists(log_path):
    os.makedirs(log_path)

if not os.path.exists(alert_data_path):
    os.makedirs(alert_data_path)

if not os.path.exists(audio_path):
    os.makedirs(audio_path)


def load_configuration():
    global config_data
    try:
        with open(os.path.join(config_path, config_file), 'r') as f:
            config_data = json.load(f)

        logger = CustomLogger(config_data.get("log_level", 1), f'{app_name}',
                              os.path.abspath(os.path.join(log_path, log_file_name))).logger
        logger.info(f'Successfully loaded configuration from {os.path.join(config_path, config_file)}')
        return {'success': True,
                'alert': {'type': 'danger',
                          'message': f'Successfully loaded configuration from {os.path.join(config_path, config_file)}'},
                'config_data': config_data}, logger

    except FileNotFoundError:
        print(f'Configuration file {os.path.join(config_path, config_file)} not found. Creating default.')
        try:
            save_config(config_path)
            # Load the newly created configuration file
            return load_configuration()
        except Exception as e:
            print(f'Error creating default configuration file: {e}')
            return {'success': False, 'alert': {'type': 'danger',
                                                'message': f'Error creating default configuration file: {e}'}}, False
    except json.JSONDecodeError:
        print(f'Configuration file {os.path.join(config_path, config_file)} is not in valid JSON format.')
        return {'success': False, 'alert': {'type': 'danger',
                                            'message': f'Configuration file {os.path.join(config_path, config_file)} is not in valid JSON format.'}}, False
    except Exception as e:
        print(f'Configuration file {config_file} is not in valid JSON format.')
        return {'success': False, 'alert': {'type': 'danger',
                                            'message': f'Unexpected Error Loading Configuration file {os.path.join(config_path, config_file)}.'}}, False


def start_canada_cap_thread(db, config_data):
    global active_threads
    # Stop the existing thread if it's running
    ca_cap_shared_state.stop_signal = True

    # Wait a bit for the threads to catch up with the signal
    time.sleep(2)

    # Clear the stop signal for the new thread
    ca_cap_shared_state.stop_signal = False

    # Start a new thread
    threading.Thread(target=canada_cap_stream, args=(db, config_data), daemon=True).start()


config_loaded, logger = load_configuration()
if not config_loaded.get("success", False):
    exit(1)

try:
    db = SQLiteDatabase(db_path=config_data["sqlite"]["database_path"])
    logger.info("SQLite Database connected successfully.")
except Exception as e:
    logger.error(f'Error while <<connecting>> to the <<database:>> {e}')
    exit(1)

app = Flask(__name__)

try:
    with open(os.path.join(config_path, 'secret_key.txt'), 'rb') as f:
        app.config['SECRET_KEY'] = f.read()
except FileNotFoundError:
    secret_key = os.urandom(24)
    with open(os.path.join(config_path, 'secret_key.txt'), 'wb') as f:
        f.write(secret_key)
    app.config['SECRET_KEY'] = secret_key

app.static_folder = 'static'


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('logged_in') is None:
            return redirect(url_for('index', next=request.url))
        return f(*args, **kwargs)

    return decorated_function


@app.route('/', methods=['GET'])
def index():
    return render_template("index.html")


@app.route('/admin', methods=['GET'])
@login_required
def admin():
    return render_template("admin.html")


@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']

    result = authenticate_user(db, username, password)

    if not result["success"]:
        flash(result.get("message"), 'danger')
        return redirect(url_for('index'))
    else:
        flash(result.get("message"), 'success')
        return redirect(url_for('admin'))


@app.route("/logout")
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))


@app.route("/get_alerts")
def route_get_alerts():
    geocode = request.args.get("geocode", None)
    identifier = request.args.get("ident", None)
    active = request.args.get("active", True)

    result = get_alerts(db, identifier=identifier, geocode=geocode, active_only=active)

    return jsonify(result)


@app.route("/api/test_alert", methods=["POST"])
def route_test_alert():
    type = request.args.get("type", "CA")
    file = request.files.get('file')
    if not file:
        return jsonify({"status": "error", "message": "No file uploaded"}), 400

    xml_data = file.read()
    if type == "CA":
        process_alert(db, config_data, xml_data)
    return jsonify({"status": "ok", "message": "Processing XML"}), 200


if config_data["canada_cap_stream"].get("enabled", 0) == 1:
    start_canada_cap_thread(db, config_data)

area_configs = config_data["canada_cap_stream"].get("alert_areas", [])
for area in area_configs:
    if area["alert_broadcast"].get("enabled", 0) == 1:
        logger.info(f"Initializing audio for {area.get('area_name')}")
        audio_relay = AudioRelay(config_data, area.get("area_id"), area["alert_broadcast"].get('input_alert_audio_sink'),
                   area["alert_broadcast"].get('input_stream_audio_sink'),
                   area["alert_broadcast"].get('output_audio_sink'))
        audio_relay.start()
        time.sleep(3)
        try:
            ic_streamer = IcecastStreamer(area["alert_broadcast"])
            ic_streamer.start()
        except Exception as e:
            traceback.print_exc()
            logger.error(e)

# if __name__ == '__main__':
#     app.run(host="0.0.0.0", port=8002, debug=False)
