const statePill = document.getElementById("state-pill");
const connectionPill = document.getElementById("connection-pill");
const messageEl = document.getElementById("message");
const coreShell = document.getElementById("core-shell");
const canvas = document.getElementById("particle-canvas");
const ctx = canvas.getContext("2d");

const particles = [];
let currentState = "idle";

const stateLabels = {
  idle: "IDLE",
  ouvindo: "OUVINDO",
  pensando: "PENSANDO",
  falando: "FALANDO",
  erro: "ERRO",
};

function resizeCanvas() {
  const dpr = window.devicePixelRatio || 1;
  canvas.width = canvas.clientWidth * dpr;
  canvas.height = canvas.clientHeight * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function seedParticles() {
  particles.length = 0;
  const total = 160;
  const radius = Math.min(canvas.clientWidth, canvas.clientHeight) * 0.26;
  const cx = canvas.clientWidth / 2;
  const cy = canvas.clientHeight / 2;

  for (let i = 0; i < total; i += 1) {
    const angle = Math.random() * Math.PI * 2;
    const distance = radius + (Math.random() - 0.5) * radius * 0.7;
    particles.push({
      angle,
      distance,
      speed: 0.001 + Math.random() * 0.003,
      size: 0.8 + Math.random() * 2.4,
      alpha: 0.15 + Math.random() * 0.45,
      orbit: (Math.random() - 0.5) * 0.15,
      jitter: Math.random() * 10,
      cx,
      cy,
    });
  }
}

function getStateEnergy() {
  if (currentState === "falando") return 1.35;
  if (currentState === "pensando") return 1.05;
  if (currentState === "ouvindo") return 1.18;
  if (currentState === "erro") return 0.85;
  return 0.92;
}

function animateParticles(time) {
  ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight);
  const energy = getStateEnergy();

  particles.forEach((particle, index) => {
    particle.angle += particle.speed * energy;
    const wobble = Math.sin(time * 0.0015 + particle.jitter) * 18 * energy;
    const x = particle.cx + Math.cos(particle.angle + particle.orbit) * (particle.distance + wobble);
    const y = particle.cy + Math.sin(particle.angle) * (particle.distance + wobble);

    const gradient = ctx.createRadialGradient(x, y, 0, x, y, particle.size * 7);
    gradient.addColorStop(0, `rgba(255, 224, 162, ${particle.alpha})`);
    gradient.addColorStop(1, "rgba(255, 122, 34, 0)");

    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(x, y, particle.size * energy, 0, Math.PI * 2);
    ctx.fill();

    if (index % 6 === 0) {
      ctx.strokeStyle = `rgba(255, 142, 54, ${particle.alpha * 0.35})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(particle.cx, particle.cy);
      ctx.lineTo(x, y);
      ctx.stroke();
    }
  });

  requestAnimationFrame(animateParticles);
}

function applyState(state, message) {
  currentState = state || "idle";
  statePill.textContent = stateLabels[currentState] || currentState.toUpperCase();
  statePill.className = `state-pill ${currentState}`;
  coreShell.className = `core-shell ${currentState}`;
  if (message) {
    messageEl.textContent = message;
  }
}

function connectWebSocket() {
  const wsHost = window.location.hostname || "127.0.0.1";
  const socket = new WebSocket(`ws://${wsHost}:8765`);

  socket.addEventListener("open", () => {
    connectionPill.textContent = "ONLINE";
    connectionPill.className = "connection-pill online";
  });

  socket.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    applyState(payload.estado, payload.mensagem);
  });

  socket.addEventListener("close", () => {
    connectionPill.textContent = "OFFLINE";
    connectionPill.className = "connection-pill offline";
    setTimeout(connectWebSocket, 1500);
  });
}

window.addEventListener("resize", () => {
  resizeCanvas();
  seedParticles();
});

resizeCanvas();
seedParticles();
requestAnimationFrame(animateParticles);
connectWebSocket();
