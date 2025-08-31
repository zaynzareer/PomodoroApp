import os
#import sys
import time
import json
import psutil
import threading
import logging
from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.serving import make_server
from datetime import datetime, timedelta
import win32gui, win32process
import ctypes
from AppNames import get_app_name


# === CONFIGURATION ===
TRACKING_INTERVAL = 10  # seconds
TOP_APP_LIMIT = 5
DEBOUNCE_THRESHOLD = 5
IDLE_THRESHOLD = 90  # seconds
DATA_FILE = 'usage_data.json'

# === SETUP ===
app = Flask(__name__)
CORS(app)

# === GLOBALS ===
app_usage = {} # In seconds
last_active_window = None
last_check_time = datetime.now()
shutting_down = False
lock = threading.Lock()

# === LOGGER ===
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s', handlers=[
        logging.FileHandler("usage_tracker.log")])

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

# === TRACKING FUNCTIONALITY ===
def get_active_window_process(): 
    try: 
        window = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(window)
        pid = win32process.GetWindowThreadProcessId(window)[1]  
        process = psutil.Process(pid)
        logging.info(f"Active title: {title} Active process: {process.name()} (PID: {pid})") 

        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and proc.info['name'].replace('.exe', '').lower() in title.lower():
                    logging.info(f"Matched process: {proc.info['name']} (PID: {proc.info['pid']})")
                    return title, get_app_name(proc.info['name'])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        logging.info(f"No matching process found for title: {title}")
        return title, get_app_name(process.name())  # If no match found, return process name as fallback

    except Exception as e:
        logging.warning(f"Error getting active window: {e}")
        return None, None

def track_app_usage():
    global last_active_window, last_check_time
    try: 
        now = datetime.now()

        # First time initialization
        if last_active_window is None:
            window_title, app_name = get_active_window_process()
            last_active_window = app_name
            last_check_time = now
            logging.info(f"Initialized tracking with app: {app_name}")
            return

        elapsed = (now - last_check_time).total_seconds()
        if elapsed <= 0:
            last_check_time = now
            return

        # Check idle now and compute how much of elapsed was active
        idle_seconds = get_idle_duration()
        if idle_seconds >= IDLE_THRESHOLD:
            # User is idle now. Assume they became idle `idle_seconds` ago.
            active_time = max(0, elapsed - idle_seconds)
            if active_time > 0 and last_active_window:
                with lock:
                    app_usage[last_active_window] = app_usage.get(last_active_window, 0) + active_time
                logging.info(f"[User Idle] Attributed {active_time:.2f}s to {last_active_window} before idle")
            # reset trackers — don't count idle as app usage
            last_check_time = now
            last_active_window = None
            return

        # Not idle: attribute the elapsed to the app that was active during the last interval
        if last_active_window:
            with lock:
                app_usage[last_active_window] = app_usage.get(last_active_window, 0) + elapsed
            logging.info(f"[Attributed] +{elapsed:.2f}s -> {last_active_window}")

        # Get the current active window and decide if switch happened
        window_title, app_name = get_active_window_process()

        if app_name != last_active_window:
            if elapsed >= DEBOUNCE_THRESHOLD:
                logging.info(f"[switch] {last_active_window} -> {app_name}")
                last_active_window = app_name
            else:
                logging.info(f"[Debounce]  {last_active_window} -> {app_name} ignored")

        last_check_time = now
    except Exception as e:
        logging.error(f"Error tracking app usage: {e}")

def tracking_loop( ):
    while True:
        track_app_usage()
        if shutting_down:
            break
        time.sleep(TRACKING_INTERVAL)


# === DATA PERSISTENCE ===
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
def reset_tracking():
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

@app.route('/shutdown', methods=['POST'])
def shutdown():
    global shutting_down
    save_usage_to_file()
    def do_shutdown():
        global shutting_down
        time.sleep(0.5)  # Give some time for the request to be processed
        flask_thread.shutdown() # Shutdown the Flask server 
        flask_thread.join()  # Wait for the server thread to finish
        shutting_down = True

    threading.Thread(target=do_shutdown).start()
    logging.info('Request to shutdown has been sent')
    return jsonify({"message": "Server is shutting down..."}), 200



# === STARTING THE SERVER ===
if __name__ == '__main__':
    load_usage_from_file()
    last_check_time = datetime.now()
    threading.Thread(target=tracking_loop, daemon=True).start()
    flask_thread.start()
    try:
        while flask_thread.is_alive() and not shutting_down:
            time.sleep(0.5)  # Keep the main thread alive while the server is running
    # Handle forceful shutdown using Ctrl+C (likely only during testing)
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt received, shutting down server...")
        flask_thread.shutdown()
        flask_thread.join()
        shutting_down = True
    logging.info("Server has been shut down gracefully.")
    #sys.exit(0)
