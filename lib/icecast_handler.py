import threading
import time
from threading import Thread

import gi
import logging

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject
from lib.icecast_thread_shared_state import icecast_shared_state

Gst.init(None)

module_logger = logging.getLogger("icad_cap_alerts.icecast")


class IcecastStreamer:
    def __init__(self, area_config):
        self.pipeline = Gst.Pipeline.new("icecast-streaming-pipeline")
        self.icecast_config = area_config.get("icecast", {})
        if not self.icecast_config:
            raise Exception("Missing icecast config")

        self.alert_broadcast_config = area_config
        if not self.alert_broadcast_config:
            raise Exception("Missing Broadcast Config")

        # Create elements
        self.source = Gst.ElementFactory.make("pulsesrc", "source")
        self.encoder = Gst.ElementFactory.make("lamemp3enc", "encoder")
        self.shout2send = Gst.ElementFactory.make("shout2send", "shout2send")

        if not all([self.source, self.encoder, self.shout2send]):
            raise Exception("GStreamer elements could not be created. Missing plugin?")

        # Set element properties
        self.source.set_property("device", f'{self.alert_broadcast_config.get("output_audio_sink")}.monitor')
        if self.icecast_config.get("bitrate", 0) != 0:
            self.encoder.set_property('target', 1)
            self.encoder.set_property('bitrate', self.icecast_config.get("bitrate"))
            self.encoder.set_property('cbr', True)
        else:
            self.encoder.set_property("bitrate", 32)
        self.shout2send.set_property("ip", self.icecast_config.get("host"))
        self.shout2send.set_property("port", int(self.icecast_config.get("port")))
        self.shout2send.set_property("mount", self.icecast_config.get("mount"))
        self.shout2send.set_property("password", self.icecast_config.get("password"))
        self.shout2send.set_property("streamname", self.icecast_config.get("stream_name"))
        self.shout2send.set_property('description', self.icecast_config.get("description"))

        # Add elements to pipeline
        self.pipeline.add(self.source)
        self.pipeline.add(self.encoder)
        self.pipeline.add(self.shout2send)

        # Link elements
        self.source.link(self.encoder)
        self.encoder.link(self.shout2send)

        # Create a bus and set up a message handler
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect("message", self.on_message)

        self.running = False
        self.icecast_id = self.icecast_config.get("stream_name", area_config.get("area_id"))
        self.thread = Thread(target=self.run)

    def on_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            module_logger.error(f"Error: {err}, {debug}")
            self.attempt_reconnect()
        elif t == Gst.MessageType.EOS:
            module_logger.info("End-Of-Stream reached.")
            self.attempt_reconnect()

    def attempt_reconnect(self):
        if self.running:
            module_logger.info("Attempting to reconnect...")
            self.stop()
            time.sleep(2)  # Wait before attempting to reconnect
            self.start()
        else:
            self.stop()

    def run(self):
        try:
            while self.running:
                time.sleep(1)  # Sleep to prevent high CPU usage
                if not icecast_shared_state.ic_shared[self.icecast_id]["stop_signal"]:
                    if self.pipeline.get_state(0).state != Gst.State.PLAYING:
                        self.attempt_reconnect()
        except Exception as e:
            module_logger.error(e)
        finally:
            self.stop()

    def update_metadata(self, **metadata):
        """Update the stream metadata.

        Args:
            metadata (dict): A dictionary of metadata key-value pairs.
        """
        taglist = Gst.TagList.new_empty()
        for key, value in metadata.items():
            taglist.add_value(Gst.TagMergeMode.REPLACE_ALL, key, value)
        self.shout2send.set_taglist(taglist)

    def start(self):
        if not self.running:
            icecast_shared_state.ic_shared[self.icecast_id] = {}
            icecast_shared_state.ic_shared[self.icecast_id]["stop_signal"] = False
            self.running = True
            module_logger.info(
                f"Starting stream... {self.icecast_id} on {self.alert_broadcast_config.get('output_audio_sink')}")
            ret = self.pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                module_logger.error(f"Failed to start streaming pipeline for {self.icecast_id}")
                self.running = False
                return
            self.thread.start()
            module_logger.info(f"Streaming thread started for {self.icecast_id}")

    def stop(self):
        self.running = False
        icecast_shared_state.ic_shared[self.icecast_id]["stop_signal"] = True
        module_logger.info(f"Stopping stream... {self.icecast_id}")
        self.pipeline.set_state(Gst.State.NULL)
        time.sleep(1.5)
        if self.thread.is_alive():
            if threading.current_thread() != self.thread:
                self.thread.join()
