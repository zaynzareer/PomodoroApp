import os
import time
import json
import psutil
import threading
import logging
from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.serving import make_server
from datetime import datetime
import win32gui, win32process
import ctypes
from ctypes import wintypes
from AppNames import get_app_name


# === CONFIGURATION ===
TOP_APP_LIMIT = 5
DEBOUNCE_THRESHOLD = 5
IDLE_THRESHOLD = 90  # seconds
DATA_FILE = 'usage_data.json'
HOOK_DEBOUNCE = 1

# === SETUP ===
app = Flask(__name__)
CORS(app)

# === GLOBALS ===
app_usage = {} # In seconds
last_active_window = None
shutting_down = False

last_switch_monotonic = None
app_usage_lock = threading.Lock()

hook_thread = None
hook_handle = None

tracking_paused = False
pause_lock = threading.Lock()


# === LOGGER ===
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s', handlers=[
        logging.FileHandler("usage_tracker.log")])

# Disable logging when not debugging 
#logging.disable(logging.CRITICAL)

# Win32 constants
EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000

# Define WinEventProc callback prototype
WinEventProcType = ctypes.WINFUNCTYPE(
    None,
    wintypes.HANDLE,  # hWinEventHook
    wintypes.DWORD,   # event
    wintypes.HWND,    # hwnd
    wintypes.LONG,    # idObject
    wintypes.LONG,    # idChild
    wintypes.DWORD,   # dwEventThread
    wintypes.DWORD    # dwmsEventTime
)

# Load user32.dll
user32 = ctypes.WinDLL("user32", use_last_error=True)

# Function prototypes
user32.SetWinEventHook.restype = wintypes.HANDLE
user32.SetWinEventHook.argtypes = [
    wintypes.DWORD, wintypes.DWORD,
    wintypes.HMODULE, WinEventProcType,
    wintypes.DWORD, wintypes.DWORD, wintypes.UINT
]

user32.UnhookWinEvent.restype = wintypes.BOOL
user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]

user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL


# === IDLE TIME DETECTION ===
def get_idle_duration():
    # We are using python ctypes as a translator to call Win32 C functions
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [('cbSize', ctypes.c_uint), ('dwTime', ctypes.c_uint)]
#     The above basically means in C:
#     typedef struct {
#     UINT cbSize;
#     UINT dwTime;
#     } LASTINPUTINFO;
    lii = LASTINPUTINFO() # Create an instance of the structure 
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO) # Set the size of the structure
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)) # Call the Win32 function to get the last input info
    millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime # Get the time since the last input in milliseconds
    return millis / 1000  # returns idle time in seconds


# Get active window's process name and title
def get_process_from_hwnd(hwnd):
    try:
        if not hwnd:
            return None, None
        title = win32gui.GetWindowText(hwnd) or ""
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            proc = psutil.Process(pid)
            proc_name = proc.name()
        except Exception as e:
            proc_name = f"pid:{pid}"
            logging.warning(f"Could not get process name for PID {pid}: {e}")
        return title, get_app_name(proc_name)
    except Exception as e:
        logging.error(f"Error getting process from hwnd: {e}")
        return None, None


# === HOOK CALLBACK ===
def win_event_proc(hWinEventHook, event, hwnd, idObject, idChild, dwEventThread, dwmsEventTime):

    if shutting_down or tracking_paused:
        return
    
    global last_switch_monotonic, last_active_window, app_usage  
    
    try:
        now = time.monotonic()

        # Initialize
        if last_switch_monotonic is None:
            title, proc_name = get_process_from_hwnd(hwnd)
            last_switch_monotonic = now
            last_active_window = proc_name
            logging.info(f"[hook init] active app = {proc_name}, title = {title}")
            return

        elapsed = now - last_switch_monotonic
        if elapsed <= 0:
            last_switch_monotonic = now
            return

        # Idle time calculation (if any)
        idle_time = get_idle_duration()

        active_time = elapsed
        if idle_time >= IDLE_THRESHOLD:
            active_time = max(0.0, elapsed - idle_time)

        # Attribution to previous active window
        if last_active_window and active_time > 0:
            with app_usage_lock:
                app_usage[last_active_window] = app_usage.get(last_active_window, 0.0) + active_time
            logging.info(f"[hook attribute] {last_active_window} -> elapsed: {elapsed}")

        # New foreground process
        title, new_proc = get_process_from_hwnd(hwnd)

        # If user is idle now, clear active window
        if idle_time >= IDLE_THRESHOLD:
            last_active_window = None
            last_switch_monotonic = now
            logging.info("[hook] user is idle — cleared last_active_window")
            return

        # Debounce very short switches
        # Do not update last_active_window or last_switch_monotonic (so we keep attributing to previous window)
        if elapsed < HOOK_DEBOUNCE:
            logging.info(f"[hook debounce] Ignored transient switch to {new_proc} (elapsed {elapsed:.3f}s)")
            return

        # Set new active window
        last_active_window = new_proc
        last_switch_monotonic = now
        logging.info(f"[hook switch] Now active = {new_proc} | Title = {title}")
    
    except Exception as e:
        logging.info(f"Error in win_event_proc: {e}")


# === HOOK MANAGEMENT ===
def install_hook():
    global hook_handle, WinEventProc

    # Create a ctypes callback wrapper
    WinEventProc = WinEventProcType(win_event_proc)

    hook_handle = user32.SetWinEventHook(
        EVENT_SYSTEM_FOREGROUND,
        EVENT_SYSTEM_FOREGROUND,
        0,
        WinEventProc,
        0, 0,
        WINEVENT_OUTOFCONTEXT
    )

    if not hook_handle:
        err = ctypes.get_last_error()
        raise ctypes.WinError(err)

    logging.info("WinEvent hook installed")

def uninstall_hook():
    global hook_handle
    if hook_handle:
        user32.UnhookWinEvent(hook_handle)
        logging.info("WinEvent hook uninstalled")
        hook_handle = None

def pump_thread_main():

    try:
        install_hook()
        logging.info("Message pump running")
        msg = wintypes.MSG()
        # Pump messages until WM_QUIT is posted
        while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) != 0:
            pass
    except Exception as e:
        logging.info("pump_thread_main failed: {e}")
    finally:
        uninstall_hook()
        logging.info("Pump thread exiting")
        
def start_hook():
    global hook_thread
    if hook_thread and hook_thread.is_alive():
        return
    hook_thread = threading.Thread(target=pump_thread_main, daemon=True)
    hook_thread.start()
    seed_hook_state()
    logging.info("Hook thread started") 

def stop_hook(timeout=2.0):
    # Stop the hook by posting a quit message and joining the thread
    try:
        user32.PostQuitMessage(0)
    except Exception as e:
        logging.exception("Failed to PostQuitMessage: {e}")
    # join thread
    if hook_thread:
        hook_thread.join(timeout)
        logging.info("Hook thread joined")


# === PAUSE/RESUME TRACKING ===

def seed_hook_state():
    # Set last_active_window and last_switch_monotonic to current foreground state.
    # We call this on resume so we don't attribute paused time.
    global last_switch_monotonic, last_active_window
    try:
        hwnd = win32gui.GetForegroundWindow()
        title, proc_name = get_process_from_hwnd(hwnd)
        last_switch_monotonic = time.monotonic()
        last_active_window = proc_name
        logging.info(f"[seed] active={proc_name} title={title}")
    except Exception:
        logging.exception("Failed to seed hook state on resume")


def pause_tracking():
    global tracking_paused, last_active_window, last_switch_monotonic
    with pause_lock:
        tracking_paused = True
        # Clear baseline so no attribution after resume from old events
        last_active_window = None
        last_switch_monotonic = time.monotonic()
        logging.info("Tracking paused")


def resume_tracking():
    # Resume attribution. Seed the current active window
    global tracking_paused
    with pause_lock:
        tracking_paused = False
        # seed the hook baseline so attribution starts fresh from now
        seed_hook_state()
        logging.info("Tracking resumed")


# === DATA MANAGEMENT ===
def save_usage_to_file(archive=False):
    data = {
        "date": str(datetime.now()),
        "usage": app_usage
    }
    filename = DATA_FILE
    if archive:
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        filename = f"archive_usage_{timestamp}.json"
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        logging.info(f"Usage data saved to {filename}")
    except Exception as e:
        logging.error(f"Failed to save data: {e}")

def load_usage_from_file():
    global app_usage
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                app_usage.update(data.get("usage", {}))
            logging.info("Previous usage data loaded.")
        except Exception as e:
            logging.warning(f"Failed to load usage data: {e}")

def get_top_apps(limit=TOP_APP_LIMIT):
    sorted_apps = sorted(app_usage.items(), key=lambda x: x[1], reverse=True)
    # return [{"name": app, "timeUsed": round(time, 2)} for app, time in sorted_apps[:limit]]
    result = []
    for app, time in sorted_apps[:limit]:
        mins = time / 60
        rounded_time = round(mins)
        result.append({"name": app, "timeUsed": rounded_time})
    return result

# === SERVER THREAD ===
class ServerThread(threading.Thread) :
    def __init__(self, app, host='127.0.0.1', port=5000):
        super().__init__()
        self.server = make_server(host, port, app)
        self.ctx = app.app_context()
        self.ctx.push()
        self.daemon = True  # Ensure the thread exits when the main program does
    def run(self):
        logging.info(f"Starting Flask server on port {self.server.port}")
        self.server.serve_forever()
    def shutdown(self):
        logging.info("Shutting down Flask server")
        self.server.shutdown()


flask_thread = ServerThread(app)


# === FLASK ROUTES ===

@app.route('/api/app-usage', methods=['GET'])
def get_app_usage():
    return jsonify(get_top_apps())

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok"})

@app.route('/api/reset-app-usage', methods=['POST'])
def reset_app_usage():
    global app_usage
    #save_usage_to_file(archive=True)
    app_usage.clear()
    logging.info("Tracking data has been reset.")
    return jsonify({"status": "success", "message": "Tracking data reset."})

@app.route('/api/mock-app-usage', methods=['GET'])
def get_mock_app_usage():
    return jsonify([
        {"name": "VS Code", "timeUsed": 120},
        {"name": "Chrome", "timeUsed": 85},
        {"name": "Slack", "timeUsed": 45},
        {"name": "Spotify", "timeUsed": 30},
        {"name": "Terminal", "timeUsed": 25}
    ])

@app.route('/api/pause-tracking', methods=['POST'])
def api_pause_tracking():
    try:
        pause_tracking()
        return jsonify({"status": "paused"})
    except Exception:
        logging.exception("Error in /api/pause-tracking")
        return jsonify({"status":"error"}), 500

@app.route('/api/resume-tracking', methods=['POST'])
def api_resume_tracking():
    try:
        resume_tracking()
        return jsonify({"status":"resumed"})
    except Exception:
        logging.exception("Error in /api/resume-tracking")
        return jsonify({"status":"error"}), 500

@app.route('/shutdown', methods=['POST'])
def shutdown():
    global shutting_down
    def do_shutdown():
        global shutting_down
        stop_hook()
        flask_thread.shutdown() # Shutdown the Flask server 
        flask_thread.join()  # Wait for the server thread to finish
        shutting_down = True

    threading.Thread(target=do_shutdown).start()
    logging.info('Request to shutdown has been sent')
    return jsonify({"message": "Server is shutting down..."}), 200



# === STARTING THE SERVER ===
if __name__ == '__main__':

    load_usage_from_file()

    start_hook()
    flask_thread.start()

    while flask_thread.is_alive() and not shutting_down:
        time.sleep(0.5)  # Keep the main thread alive while the server is running

    # On shutdown, save data
    save_usage_to_file()
    logging.info("Server has been shut down gracefully.")