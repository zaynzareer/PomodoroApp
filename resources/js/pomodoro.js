let totalTime =  25 * 60  ;
let time = 25 * 60; // 25 mins: 25 *60
let timerInterval = null;
let isRunning = false;
let pomodoros = 0;
let breakDuration = 5 * 60 ;
const timerProgress = document.getElementById("timerProgress");
const startButton = document.getElementById("startTimer");

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
    timerInterval = setInterval(() => {
      if (time > 0) {
        time--;
        updateDisplay();
      } else {
        clearInterval(timerInterval);
        pomodoros++;
        document.getElementById('pomodoros').innerText = pomodoros;
        isRunning = false;
        showBreakWindow();
        playSound();
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
  totalTime = 25 * 60;
  time = 25 * 60;
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
  enableInspector: true,
  resizable: false,
  hidden: false
  });

  // Start checking local storage
  if (checkBreakstatus) {
    stopCheckingBreakstatus();
  }
  if (breakDuration < 5) {
    startCheckingBreakstatus();
  } 
  else {
    breakstatusTimeout = setTimeout(startCheckingBreakstatus, (breakDuration - 3) * 1000);
  }
};

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
          playSound2();
          resetTimer();
          toggleTimer();  
        }
      }
    } catch (e) {
      console.log("Error while reading storage: ", e);
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

function playSound() {
  let audio = new Audio("sounds/EndFocus.mp3");
  audio.play();
}

function playSound2() {
  let audio = new Audio("sounds/EndBreak.mp3");
  audio.play();
}