let totalTime =  20 * 60; // 20 mins: 20 *60
let time = 20 * 60; 
let timerInterval = null;
let isRunning = false;
let pomodoros = 0;
let breakDuration = 5 * 60 ;
const timerProgress = document.getElementById("timerProgress");
const startButton = document.getElementById("startTimer");

Neutralino.init();

function updateDisplay() {
  let minutes = Math.floor(time / 60).toString().padStart(2, '0');
  let seconds = (time % 60).toString().padStart(2, '0');
  document.getElementById('timer').innerText = `${minutes}:${seconds}`;

  // Timer Animation
  const progressPercentage = ((totalTime - time) / totalTime) * 100;
  timerProgress.style.background = `conic-gradient(
      var(--primary-color) ${progressPercentage}%, 
      transparent ${progressPercentage}%
  )`
}

updateDisplay(); // initialize display

let breakstatusTimeout = null;

// Toggle timer state
function toggleTimer() {
  if (isRunning) {
    clearInterval(timerInterval);
    startButton.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polygon points="5 3 19 12 5 21 5 3"></polygon>
      </svg>
      Resume
    `;
  } else {
    stopCheckingBreakstatus();
    timerInterval = setInterval(async() => {
      if (time > 0) {
        time--;
        updateDisplay();
      } else {
        clearInterval(timerInterval);
        pomodoros++;
        document.getElementById('pomodoros').innerText = pomodoros;
        isRunning = false;
        await showBreakWindow();
        endFocusSound();
      }
    }, 1000);
    
    startButton.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="6" y="4" width="4" height="16"></rect>
        <rect x="14" y="4" width="4" height="16"></rect>
      </svg>
      Pause
    `;
  }
  
  isRunning = !isRunning;
}

function resetTimer() {
  if(isRunning){
    toggleTimer();
  }
  //time = 25 * 60;
  totalTime = 20 * 60;
  time = 20 * 60;
  updateDisplay();
}

async function showBreakWindow() {

  await Neutralino.storage.setData("BreakDuration", JSON.stringify({ duration: breakDuration }));

  Neutralino.window.create(
  '/break.html',
  {
  title: 'Break Time!',
  width: 1200,
  height: 700,
  alwaysOnTop: true,
  borderless: true,
  fullScreen: false,
  enableInspector: false,
  resizable: false,
  hidden: false
  });

  // Start checking local storage
  if (checkBreakstatus) {
    stopCheckingBreakstatus();
  }
  else {
    startCheckingBreakstatus();
  }
};

async function resume_tracking() {
  try {
    const res = await fetch('http://localhost:5000/api/resume-tracking', {method: 'POST'});
  } catch (e) {
    console.error("Could not shut down backend server:", e);
  }
}

let checkBreakstatus = null;

function startCheckingBreakstatus() {
  if (checkBreakstatus) return;
  checkBreakstatus = setInterval( async () => { 
    try {
      let storageData = await Neutralino.storage.getData("BreakStatus");
      if (storageData) {
        let data = JSON.parse(storageData);
        if (data.ended) {
          console.log("Ended msg successfully recieved from local Storage!");
          Neutralino.storage.setData("BreakStatus", null);
          endBreakSound();
          resetTimer();
          toggleTimer();
          setTimeout(await resume_tracking(), 1000);
        }
      }
    } catch (e) {
      // Do nothing if data not found
    }
  }, 1000);
}

function stopCheckingBreakstatus() {
  if (checkBreakstatus) {
    clearInterval(checkBreakstatus);
    checkBreakstatus = null;
  }
  if (breakstatusTimeout) {
    clearTimeout(breakstatusTimeout);
    breakstatusTimeout = null;
  }
}

// Sound Effects
function endFocusSound() {
  let audio = new Audio("sounds/EndFocus.mp3");
  audio.play();
}

function endBreakSound() {
  let audio = new Audio("sounds/EndBreak.mp3");
  audio.play();
}



// App Usage Tracking
const chartColors = [
  '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF',
  '#FF9F40', '#66BB6A', '#EF5350', '#AB47BC', '#26C6DA'
];

let appUsageChart = null;

function createAppUsageChart(data) {
  const ctx = document.getElementById('appUsageChart').getContext('2d');

  // Destroy previous chart instance to avoid duplicates
  if (appUsageChart) {
    appUsageChart.destroy();
  }

  // Create new chart
  appUsageChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.apps,
      datasets: [{
        label: 'Minutes Used',
        data: data.timeUsed,
        backgroundColor: chartColors.slice(0, data.apps.length),
        borderColor: 'rgba(0, 0, 0, 0.1)',
        borderWidth: 1,
        borderRadius: 6,
        barThickness: 20,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          backgroundColor: 'rgba(30, 30, 30, 0.8)',
          titleColor: '#EEEEEE',
          bodyColor: '#EEEEEE',
          borderColor: 'rgba(255, 87, 34, 0.3)',
          borderWidth: 1,
          cornerRadius: 8,
          padding: 12,
          bodyFont: {
            size: 14
          },
          titleFont: {
            size: 14,
            weight: 'bold'
          },
          callbacks: {
            label: function(context) {
              return `${context.raw} minutes`;
            }
          }
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          grid: {
            color: 'rgba(255, 255, 255, 0.05)',
            drawBorder: false
          },
          ticks: {
            color: '#AAAAAA',
            font: {
              size: 12
            },
            callback: function(value) {
              return value + ' min';
            }
          }
        },
        x: {
          grid: {
            display: false
          },
          ticks: {
            color: '#AAAAAA',
            font: {
                size: 12
            }
          }
        }
      }
    }
  });

  // Generate legend
  const legendContainer = document.getElementById('appLegend');
  legendContainer.innerHTML = '';

  data.apps.forEach((app, i) => {
    const legendItem = document.createElement('div');
    legendItem.className = 'legend-item';

    const colorBox = document.createElement('div');
    colorBox.className = 'legend-color';
    colorBox.style.backgroundColor = chartColors[i];

    const label = document.createElement('span');
    label.textContent = app;

    legendItem.appendChild(colorBox);
    legendItem.appendChild(label);
    legendContainer.appendChild(legendItem);
  });
}

async function startPythonServer() {
  try {
    const pythonScript = Neutralino.os.execCommand('python C:\\Users\\zayn\\Desktop\\Pomodoro\\resources\\backend\\UsageTracker.py', {background: true});
  } catch (err) {
    console.error("Failed to start Flask server:", err);
  }
}

async function waitForBackendReady(retries = 10) {
  for (let i = 0; i < retries; i++) {
    try {
      const response = await fetch('http://localhost:5000/api/health');
      if (response.ok) {
        console.log("Backend is ready.");
        hideLoadingOverlay();
        return;
      }
    } catch (err) {
      await new Promise(res => setTimeout(res, 2000));
    }
  }
    throw new Error("Backend failed to start.");
}


// Fetch app usage data from Flask backend
async function fetchAppUsageData() {
try {
  const response = await fetch('http://localhost:5000/api/app-usage');
  const rawData = await response.json();
  console.log("Raw app usage data:", rawData);

  const transformedData = {
    apps: rawData.map(app => app.name),
    timeUsed: rawData.map(app => app.timeUsed)
  };

  createAppUsageChart(transformedData);
  } catch (error) {
    console.error('Error fetching app usage data:', error);
  }
}

function hideLoadingOverlay() {
  const loadingContent = document.querySelector('.loading-container');
  loadingContent.style.opacity = '0';
  loadingContent.style.transition = 'opacity 0.9s ease-out';
  setTimeout(() => {
    loadingContent.style.display = 'none';
  }, 1000);

  setTimeout(() => {
    const loadingDone = document.querySelector('.done-container');
    loadingDone.style.display = 'block';
  }, 1000);
  setTimeout(() => {
    const loadingOverlay = document.querySelector('.loading-overlay');
    loadingOverlay.style.opacity = '0';
    loadingOverlay.style.transition = 'opacity 0.9s ease-out';
    setTimeout(() => {
      loadingOverlay.style.display = 'none';
    }, 1000);
  }, 4500);
}

function initCustomWindowTitleBar () {
  Neutralino.window.setDraggableRegion("app-header");
  Neutralino.window.setSize({
    width: 1000,
    height: 690,
  });
  Neutralino.window.unmaximize();
  Neutralino.window.move(200,25);

  // Window Controls
  document.getElementById('minimize-btn').addEventListener('click', async() => {
    await Neutralino.window.minimize();
    console.log("Window minimized");
  });

  maximizeBtn = document.getElementById('maximize-btn'); 

  maximizeBtn.addEventListener('click', async () => { 
    let isMaximized = await Neutralino.window.isMaximized();
    if (!isMaximized) {
      await Neutralino.window.maximize();
      maximizeBtn.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <!-- Back box -->
      <rect x="3" y="7" width="14" height="14" rx="1" ry="1"/>
      <!-- Front box (top right overlay) -->
      <path d="M7 3h14v14h-4"/>
      </svg> `;
      console.log("Window maximized")
    } else {
      await Neutralino.window.unmaximize();
      maximizeBtn.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
      stroke-linecap="round" stroke-linejoin="round">
      <rect x="5" y="5" width="14" height="14" rx="2" ry="2" />
      </svg> `;
      console.log("Window unmaximized");
    }
  });

  document.getElementById('close-btn').addEventListener('click', async () => {
    try {
      const res = await fetch('http://localhost:5000/shutdown', {method: 'POST'});
      if (res.ok) {
        Neutralino.debug.log("Shutdown request sent successfully.");
        await Neutralino.app.exit();
      } else {
        console.log("Shutdown request not succesfful", await res.text());
      }
    } catch (e) {
      console.error("Could not shut down backend server:", e);
    }
  });
}

async function AppUsageReset() {
  try  {
    let stored = await Neutralino.storage.getData("AppUsageResetDate");
    last_reset_date = JSON.parse(stored).last_reset_date;
    let today = new Date().getDate();
    if (last_reset_date !== today) {
      console.log("New day detected, resetting app usage data.");
      await fetch('http://localhost:5000/api/reset-app-usage', {method: 'POST'});
      await Neutralino.storage.setData("AppUsageResetDate", JSON.stringify({last_reset_date: today}));
    }
  } catch (e) {
    console.log("Could not find AppUsageResetDate in storage, setting to today. Error:", e);
    today = new Date().getDate();
    await Neutralino.storage.setData("AppUsageResetDate", JSON.stringify({last_reset_date: today}));
  }
};

let readyStatus = false;
let is_initialized = false;

Neutralino.events.on("ready", async () => {
  console.log("🛰️ Neutralino is ready");
  readyStatus = true;

  initCustomWindowTitleBar();
  // Initialize app usage data fetch
  document.addEventListener('DOMContentLoaded', async () => {
    await startPythonServer(); // Start Flask server
    await waitForBackendReady(); // Wait for backend to be ready
    is_initialized = true;
    await AppUsageReset(); // Reset app usage data if needed
    await fetchAppUsageData(); // Initial fetch
    //setInterval(fetchAppUsageData, 5 * 60 * 1000); // Refresh every 5 minutes
    setInterval(fetchAppUsageData, 10 * 1000)
  });
});

// Handle initialization errors
setTimeout( async () => {
  if (!readyStatus) {
    console.error("Neutralino failed to initialize within the expected time.");
    let button = await Neutralino.os.showMessageBox('Initialization Error',
      'The App failed to initialize. Click Ok to close the app and try opening again.',
      'OK', 'ERROR');
    if(button == 'OK') {
      await Neutralino.app.exit();
    }
  }
} , 4000);

setTimeout( async () => {
  if (!is_initialized) {
    console.error("Application failed to initialize within the expected time.");
    let button = await Neutralino.os.showMessageBox('Initialization Error',
      'The App failed to initialize. Click Ok to close the app and try opening again.',
      'OK', 'ERROR');
    if(button == 'OK') {
      await Neutralino.app.exit();
    }
  }
} , 30000);