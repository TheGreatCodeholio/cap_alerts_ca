import logging
import socket
import time
from threading import Thread

from lib.ca_cap_thread_shared_state import ca_cap_shared_state
from lib.canada_cap_alert_handler import process_alert

module_logger = logging.getLogger("icad_cap_alerts.canada_cap_stream")


class StreamConnection:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None

    def __enter__(self):
        try:
            # Create a socket object
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            # Set a timeout for the socket (optional, adjust as needed)
            self.sock.settimeout(120)

            # Connect to the server
            self.sock.connect((self.host, self.port))
            module_logger.info(f"Canada CAP Stream: Connected to {self.host}")
            return self.sock
        except socket.error as e:
            module_logger.error(f"Canada CAP Stream: Error connecting to {self.host}: {e}")
            return None

    def __exit__(self, exc_type, exc_value, traceback):
        if self.sock:
            self.sock.close()
            module_logger.info(f"Canada CAP Stream: Disconnected from {self.host}")


def connect_to_stream(host, port):
    return StreamConnection(host, port)


def canada_cap_stream(db, config_data):
    hosts = config_data["canada_cap_stream"].get("hosts", ["streaming1.naad-adna.pelmorex.com",
                                                           "streaming2.naad-adna.pelmorex.com"])
    port = config_data["canada_cap_stream"].get("port", 8080)

    while not ca_cap_shared_state.stop_signal:
        for host in hosts:
            try:
                with connect_to_stream(host, port) as sock:
                    if sock:
                        process_stream(sock, db, config_data)
                    else:
                        module_logger.error(f"Failed to connect to {host}.")

            except (socket.error, Exception) as e:
                module_logger.error(f"Canada CAP Stream: Error with stream {host}: {e}")
            finally:
                module_logger.info(
                    f"Canada CAP Stream: Attempting to reconnect in {config_data['canada_cap_stream'].get('reconnect_delay', 5)} seconds...")
                time.sleep(config_data['canada_cap_stream'].get('reconnect_delay', 5))

    module_logger.info(f"Canada CAP thread exited....")


def process_stream(sock, db, config_data):
    buffer = b''

    while True:
        if ca_cap_shared_state.stop_signal:
            module_logger.info("Canada CAP Stream: Stop signal received, thread is exiting.")
            break

        try:
            data = sock.recv(1024)
            if not data:
                module_logger.info("Canada CAP Stream: No more data received, closing connection.")
                break

            buffer += data

            if b'</alert>' in buffer:
                process_buffer(buffer, db, config_data)
                buffer = b''  # Reset the buffer after processing

        except socket.timeout as e:
            module_logger.warning(f"Canada CAP Stream: Socket timeout: {e}")
            break
        except UnicodeDecodeError as e:
            module_logger.error(f"Error decoding alert: {e}")


def process_buffer(buffer, db, config_data):
    try:
        alert_text = buffer.decode('utf-8')
        if 'NAADS-Heartbeat' in alert_text:
            module_logger.debug("Canada CAP Stream: Heartbeat received")
        else:
            Thread(target=process_alert, args=(db, config_data, alert_text), daemon=True).start()
    except UnicodeDecodeError as e:
        module_logger.error(f"Error decoding alert: {e}")
