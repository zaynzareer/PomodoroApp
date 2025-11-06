console.log("Inside break.js!!!");
Neutralino.init();
let isPaused = false;
let totalBreakDuration = 5
let breakDuration = 5; // fallback value
const timerDisplay = document.getElementById('timer');
const timerRing = document.querySelector('.timer-ring');
const pauseBtn = document.getElementById('pauseBtn');
const skipBtn = document.getElementById('skipBtn');

async function pause_tracking() {
  try {
    const res = await fetch('http://localhost:5000/api/pause-tracking', {method: 'POST'});
  } catch (e) {
    console.error("Could not shut down backend server:", e);
  }
}

async function initializeBreak() {
  
  await pause_tracking();

  try {
    const stored = await Neutralino.storage.getData('BreakDuration');
    if (stored) {
      const data = JSON.parse(stored);
      if (data.duration) {
        breakDuration = data.duration;
        totalBreakDuration = data.duration;
      }
    }
  } catch (e) {
    console.error("Could not load break duration from storage:", e);
  }

  console.log("Break Duration is:", breakDuration);
  startCountdown();
  createParticles();
}

initializeBreak();

function startCountdown() {
  updateCountdown();
  const interval = setInterval(async () => {
    if (!isPaused){
      breakDuration--;
      updateCountdown();

      if (breakDuration <= 0) {
        clearInterval(interval);
        await endBreak();
      }
    }
  }, 1000);
}

function updateCountdown() {
  const minutes = Math.floor(breakDuration / 60).toString().padStart(2, '0');
  const seconds = (breakDuration % 60).toString().padStart(2, '0');
  timerDisplay.innerText = `${minutes}:${seconds}`;

  // Update progress ring
  const progress = (breakDuration / totalBreakDuration) * 100;
  timerRing.style.setProperty('--progress', `${progress}%`);
}

pauseBtn.addEventListener('click', () => {
  isPaused = !isPaused;
  pauseBtn.innerHTML = isPaused ? 
    '<svg class="control-icon" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg> Resume' : 
    '<svg class="control-icon" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg> Pause';
});
      
skipBtn.addEventListener('click', () => {
  if(confirm("Are you sure you want to skip the break?")) {
    endBreak();
  }
});

async function endBreak() {
  try {
  await Neutralino.storage.setData("BreakStatus", JSON.stringify({ ended: true }));
  await Neutralino.app.exit();
  } catch (e) {
  console.error('Error ending break:', e);
  }
};

// Create floating particles
function createParticles() {
  const overlay = document.querySelector('.break-overlay');
  for (let i = 0; i < 20; i++) {
    const particle = document.createElement('div');
    particle.classList.add('glowing-particles');
    
    // Random positioning
    particle.style.left = `${Math.random() * 100}%`;
    particle.style.top = `${Math.random() * 100}%`;
    
    // Random size
    const size = Math.random() * 6 + 2;
    particle.style.width = `${size}px`;
    particle.style.height = `${size}px`;
    
    // Random colors between primary and secondary
    const colors = ['var(--primary-color)', 'var(--secondary-color)', 'var(--tertiary-color)', 'var(--accent-color)'];
    particle.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
    
    // Random animation duration and delay
    particle.style.animationDuration = `${Math.random() * 10 + 5}s`;
    particle.style.animationDelay = `${Math.random() * 5}s`;
    
    overlay.appendChild(particle);
  }
}