import logging
import threading
import time
import traceback

import pulsectl
from threading import Thread
from lib.pulseaudio_thread_shared_state import pulseaudio_shared_state

module_logger = logging.getLogger("icad_cap_alerts.audio_relay_handler")


class AudioRelay:
    def __init__(self, config_data, area_id, alert_sink_name, broadcast_sink_name, output_sink_name):
        self.config_data = config_data
        self.alert_sink_name = alert_sink_name
        self.broadcast_sink_name = broadcast_sink_name
        self.output_sink_name = output_sink_name
        self.area_id = area_id
        self.running = False
        self.thread = Thread(target=self.run)

    def start(self):
        if not self.running:
            pulseaudio_shared_state.pa_shared[self.area_id] = {}
            pulseaudio_shared_state.pa_shared[self.area_id]["stop_signal"] = False
            pulseaudio_shared_state.pa_shared[self.area_id]["alert_active"] = False
            self.running = True
            self.thread.start()

    def stop(self):
        self.running = False
        pulseaudio_shared_state.pa_shared[self.area_id]["stop_signal"] = True
        pulseaudio_shared_state.pa_shared[self.area_id]["alert_active"] = False
        time.sleep(1.5)
        if self.thread.is_alive():
            if threading.current_thread() != self.thread:
                self.thread.join()

    def module_exists(self, pulse, module_id):
        """Check if a module exists."""
        for module in pulse.module_list():
            if module.index == module_id:
                return True
        return False

    def unmute_sink_by_name(self, pulse, sink_name):
        """ Unmute a sink based on its name. """
        for sink in pulse.sink_list():
            if sink.name == sink_name and sink.mute == 1:
                pulse.mute(sink, 0)
                module_logger.info(f"Unmuted sink: {sink_name}")

    def unmute_source_by_name(self, pulse, source_name):
        """ Unmute a source based on its name. """
        for source in pulse.source_list():
            if source.name == source_name and source.mute == 1:
                pulse.mute(source, 0)
                module_logger.info(f"Unmuted source: {source_name}")

    def enable_loopback_for_source(self, source_name, sink_name):
        try:
            with pulsectl.Pulse('loopback_creator') as pulse:
                module_id = pulse.module_load('module-loopback', f'source={source_name} sink={sink_name}')
                self.unmute_source_by_name(pulse, source_name)
                self.unmute_sink_by_name(pulse, sink_name)
            return module_id
        except Exception as e:
            module_logger.error(f"Error enabling loopback: {e}")
            return None

    def disable_loopback_for_source(self, module_id):
        try:
            with pulsectl.Pulse('loopback_disable') as pulse:
                pulse.module_unload(module_id)
        except Exception as e:
            module_logger.error(f"Error disabling loopback: {e}")

    def create_null_sink(self, sink_name):
        with pulsectl.Pulse('sink_creator') as pulse:
            module_id = pulse.module_load('module-null-sink', f'sink_name={sink_name}')
            self.unmute_sink_by_name(pulse, sink_name)
            return module_id

    def destroy_sinks(self, sink_list):
        for sink_id in sink_list:
            module_logger.warning(f"removing Sink {sink_id}")
            self.remove_sink_by_module_id(sink_id)

    def remove_sink_by_module_id(self, module_id):
        """Remove a sink by its module ID."""
        with pulsectl.Pulse('sink_remover') as pulse:
            if self.module_exists(pulse, module_id):
                try:
                    pulse.module_unload(module_id)
                except pulsectl.pulsectl.PulseOperationFailed as e:
                    module_logger.error(f"Failed to unload module {module_id}: {e}")
            else:
                module_logger.warning(f"Module {module_id} does not exist.")

    def run(self):
        sink_ids = []
        main_loopback_module_id = None
        alert_loopback_module_id = None

        module_logger.info("Starting Audio Relay Thread")
        try:
            with pulsectl.Pulse(f'icad_cap_alerts_{self.output_sink_name}') as pulse:
                alert_sink_module_id = self.create_or_get_null_sink_module_id(pulse, self.alert_sink_name)
                output_sink_module_id = self.create_or_get_null_sink_module_id(pulse, self.output_sink_name)

                sink_ids = [alert_sink_module_id, output_sink_module_id]

                # Establish initial loopback from broadcast source to output sink
                main_loopback_module_id = self.enable_loopback_for_source(self.broadcast_sink_name,
                                                                          self.output_sink_name)

                # Initialize variable for alert loopback module ID
                alert_loopback_module_id = None

                while self.running and not pulseaudio_shared_state.pa_shared[self.area_id]["stop_signal"]:
                    if pulseaudio_shared_state.pa_shared[self.area_id]["alert_active"]:
                        if main_loopback_module_id is not None:
                            self.disable_loopback_for_source(main_loopback_module_id)
                            main_loopback_module_id = None

                        if not alert_loopback_module_id:
                            module_logger.info("Alert Activated")
                            # Assuming self.alert_sink_name is the monitor source for the alert
                            alert_loopback_module_id = self.enable_loopback_for_source(
                                f"{self.alert_sink_name}.monitor",
                                self.output_sink_name)

                    else:
                        if alert_loopback_module_id is not None:
                            module_logger.info("Alert Ended")
                            self.disable_loopback_for_source(alert_loopback_module_id)
                            alert_loopback_module_id = None

                        if main_loopback_module_id is None:
                            main_loopback_module_id = self.enable_loopback_for_source(self.broadcast_sink_name,
                                                                                      self.output_sink_name)

                    time.sleep(.5)

        except Exception as e:
            traceback.print_exc()
            module_logger.error(f"Error in AudioRelay: {e}")
            if self.running:
                module_logger.warning("Attempting to restart AudioRelay...")
                self.stop()
                self.start()

        finally:
            module_logger.warning("Closing Relay")
            # Cleanup code for loopbacks
            if main_loopback_module_id is not None:
                self.disable_loopback_for_source(main_loopback_module_id)
            if alert_loopback_module_id is not None:
                self.disable_loopback_for_source(alert_loopback_module_id)
            # Cleanup code for sinks
            self.destroy_sinks(sink_ids)

    def find_sink_input(self, pulse, name):
        for si in pulse.sink_input_list():
            #module_logger.debug(f"Sink Input: {si.name}")
            if si.name == name:
                return si
        return None

    def find_sink(self, pulse, name):
        for s in pulse.sink_list():
            #module_logger.debug(f"Sink: {s.name}")
            if s.name == name:
                return s
        return None

    def find_modules(self, pulse, name):
        for s in pulse.module_list():

            #module_logger.debug(f"Sink: {s.name}")
            if s.name == name:
                return s
        return None

    def find_monitor_source(self, pulse, sink_name):
        monitor_name = f"{sink_name}.monitor"
        for source in pulse.source_list():
            if source.name == monitor_name:
                return source
        return None

    def find_module_id_for_sink(self, pulse, sink_name):
        for module in pulse.module_list():
            #module_logger.warning(f"Module: {module.name}, Index: {module.index}, Arguments: {getattr(module, 'argument', 'N/A')}")
            if hasattr(module, 'argument') and module.argument is not None:
                if sink_name in module.argument:
                    return module.index
        return None

    def create_or_get_null_sink_module_id(self, pulse, sink_name):
        """
        Create a null sink if it doesn't exist and return its module ID.
        If it exists, return the existing module ID.
        """
        existing_sink = self.find_sink(pulse, sink_name)
        if existing_sink is not None:
            # Find the module ID for the existing sink
            module_id = self.find_module_id_for_sink(pulse, sink_name)
            if module_id is not None:
                return module_id
            else:
                # Handle the case where the sink exists but the module ID is not found
                raise Exception(f"Sink '{sink_name}' exists, but module ID not found.")

        # If the sink doesn't exist, create it
        module_id = self.create_null_sink(sink_name)
        return module_id
