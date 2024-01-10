from lib.pulseaudio_thread_shared_state import pulseaudio_shared_state
from lib.icecast_thread_shared_state import icecast_shared_state


def worker_exit(server, worker):
    for alert_area in pulseaudio_shared_state.pa_shared:
        print(pulseaudio_shared_state.pa_shared[alert_area])
        pulseaudio_shared_state.pa_shared[alert_area]["stop_signal"] = True
        print(f"Worker exiting. Stop signal set to True for Alert Broadcast {alert_area}")

    for icecast_stream in icecast_shared_state.ic_shared:
        print(icecast_shared_state.ic_shared[icecast_stream])
        icecast_shared_state.ic_shared[icecast_stream]["stop_signal"] = True
        print(f"Worker exiting. Stop signal set to True for Icecast Stream {icecast_stream}")
