/**
 * SMART PARCEL BOX – KIOSK APPLICATION CONTROLLER (ENGLISH)
 * Flow: Start -> Role -> Live Face Auth -> Shipper / Receiver Flows
 * Live camera only registration with liveness & duplicate check
 * Mandatory face re-authentication after registration
 */

// State Machine
const AppState = {
  currentScreen: 'screen-start',
  role: 'shipper', // 'shipper' | 'receiver'
  reauthMode: false,
  authenticatedUser: null,
  selectedReceiver: null,
  activeTransaction: null,
  currentLocker: null,
  failCount: 0,
  maxFailAttempts: 5,
  ws: null,
  cameraCommand: null,
  capturedEmbeddingHex: null,
};

// DOM References
const DOM = {
  // Screens
  screens: document.querySelectorAll('.screen'),
  screenStart: document.getElementById('screen-start'),
  screenRole: document.getElementById('screen-role'),
  screenFace: document.getElementById('screen-face'),
  screenRegister: document.getElementById('screen-register'),
  screenReceivers: document.getElementById('screen-receivers'),
  screenDeposit: document.getElementById('screen-deposit'),
  screenCollect: document.getElementById('screen-collect'),

  // Header / Badges
  liveClock: document.getElementById('live-clock'),
  systemStatusText: document.getElementById('system-status-text'),
  btnToggleHardware: document.getElementById('btn-toggle-hardware'),
  btnToggleAudit: document.getElementById('btn-toggle-audit'),

  // Start Screen
  btnStart: document.getElementById('btn-start'),

  // Role Screen
  cardRoleShipper: document.getElementById('card-role-shipper'),
  cardRoleReceiver: document.getElementById('card-role-receiver'),
  btnBackToStart: document.getElementById('btn-back-to-start'),

  // Face Detection Screen
  cameraOverlay: document.getElementById('camera-overlay'),
  camDetectionStatus: document.getElementById('cam-detection-status'),
  attemptDots: document.getElementById('attempt-dots'),
  attemptCountText: document.getElementById('attempt-count-text'),
  currentRoleTag: document.getElementById('current-role-tag'),
  faceModeTitle: document.getElementById('face-mode-title'),
  faceModeDesc: document.getElementById('face-mode-desc'),
  matchCard: document.getElementById('match-card'),
  matchUserName: document.getElementById('match-user-name'),
  matchUserRole: document.getElementById('match-user-role'),
  matchConfidence: document.getElementById('match-confidence'),
  matchPhone: document.getElementById('match-phone'),
  btnConfirmMatch: document.getElementById('btn-confirm-match'),
  registerPromptBox: document.getElementById('register-prompt-box'),
  btnTriggerRegister: document.getElementById('btn-trigger-register'),
  btnCancelFace: document.getElementById('btn-cancel-face'),

  // Registration Screen
  regCanvasOverlay: document.getElementById('reg-canvas-overlay'),
  regFramesCount: document.getElementById('reg-frames-count'),
  regRoleTag: document.getElementById('reg-role-tag'),
  regQualityVal: document.getElementById('reg-quality-val'),
  regQualityBar: document.getElementById('reg-quality-bar'),
  regLivenessStatus: document.getElementById('reg-liveness-status'),
  duplicateAlert: document.getElementById('duplicate-alert'),
  duplicateAlertMsg: document.getElementById('duplicate-alert-msg'),
  formRegisterUser: document.getElementById('form-register-user'),
  regInputName: document.getElementById('reg-input-name'),
  regInputPhone: document.getElementById('reg-input-phone'),
  regInputUnit: document.getElementById('reg-input-unit'),
  regInputExtId: document.getElementById('reg-input-extid'),
  labelExtId: document.getElementById('label-extid'),
  btnSubmitRegistration: document.getElementById('btn-submit-registration'),
  btnCancelRegistration: document.getElementById('btn-cancel-registration'),

  // Receiver Selection Screen
  receiversGrid: document.getElementById('receivers-grid'),
  inputSearchReceiver: document.getElementById('input-search-receiver'),
  btnBackFromReceivers: document.getElementById('btn-back-from-receivers'),

  // Deposit Screen
  depositDoorGraphic: document.getElementById('deposit-door-graphic'),
  depositLockerPlate: document.getElementById('deposit-locker-plate'),
  depositLockerLed: document.getElementById('deposit-locker-led'),
  depositDoorStatusText: document.getElementById('deposit-door-status-text'),
  depositTargetLocker: document.getElementById('deposit-target-locker'),
  depositRecName: document.getElementById('deposit-rec-name'),
  depositRecPhone: document.getElementById('deposit-rec-phone'),
  depositRecUnit: document.getElementById('deposit-rec-unit'),
  btnSimulatePlaceParcel: document.getElementById('btn-simulate-place-parcel'),
  depositCompleteCard: document.getElementById('deposit-complete-card'),
  depositCountdown: document.getElementById('deposit-countdown'),
  depositReceipt: document.getElementById('deposit-receipt'),
  receiptTxId: document.getElementById('receipt-tx-id'),
  receiptLocker: document.getElementById('receipt-locker'),
  receiptTime: document.getElementById('receipt-time'),
  btnFinishDeposit: document.getElementById('btn-finish-deposit'),

  // Collect Screen
  collectDoorGraphic: document.getElementById('collect-door-graphic'),
  collectLockerPlate: document.getElementById('collect-locker-plate'),
  collectLockerLed: document.getElementById('collect-locker-led'),
  collectDoorStatusText: document.getElementById('collect-door-status-text'),
  collectTargetLocker: document.getElementById('collect-target-locker'),
  collectRecName: document.getElementById('collect-rec-name'),
  collectRecLocker: document.getElementById('collect-rec-locker'),
  collectDepositedTime: document.getElementById('collect-deposited-time'),
  collectShipperName: document.getElementById('collect-shipper-name'),
  collectSensorFlowBox: document.getElementById('collect-sensor-flow-box'),
  btnSimulateRemoveParcel: document.getElementById('btn-simulate-remove-parcel'),
  collectCompleteCard: document.getElementById('collect-complete-card'),
  collectCountdown: document.getElementById('collect-countdown'),
  collectReceipt: document.getElementById('collect-receipt'),
  collectReceiptLocker: document.getElementById('collect-receipt-locker'),
  collectReceiptTime: document.getElementById('collect-receipt-time'),
  btnFinishCollect: document.getElementById('btn-finish-collect'),

  // Modals
  modalHardware: document.getElementById('modal-hardware'),
  btnCloseHardware: document.getElementById('btn-close-hardware'),
  lockersGridPreview: document.getElementById('lockers-grid-preview'),
  modalAudit: document.getElementById('modal-audit'),
  btnCloseAudit: document.getElementById('btn-close-audit'),
  auditTableBody: document.getElementById('audit-table-body'),
  toastContainer: document.getElementById('toast-container'),
};

// ---------------------------------------------------------------------------
// Screen Management
// ---------------------------------------------------------------------------
function showScreen(screenId) {
  DOM.screens.forEach(s => {
    s.classList.remove('active');
  });
  const target = document.getElementById(screenId);
  if (target) {
    target.classList.add('active');
    AppState.currentScreen = screenId;
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
}

// ---------------------------------------------------------------------------
// Clock & Notifications
// ---------------------------------------------------------------------------
function updateClock() {
  const now = new Date();
  const timeStr = now.toLocaleTimeString('en-US', { hour12: false });
  if (DOM.liveClock) DOM.liveClock.textContent = timeStr;
}
setInterval(updateClock, 1000);
updateClock();

function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  DOM.toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function connectWebSocket() {
  if (AppState.ws && [WebSocket.CONNECTING, WebSocket.OPEN].includes(AppState.ws.readyState)) {
    return AppState.ws;
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/camera`;
  const ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log('WebSocket connected to Edge Camera Service');
    DOM.systemStatusText.textContent = 'System Online';
    if (AppState.cameraCommand) {
      ws.send(JSON.stringify(AppState.cameraCommand));
    }
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleWebSocketMessage(msg);
    } catch (e) {
      console.error('Error parsing WS message:', e);
    }
  };

  ws.onclose = () => {
    console.log('WebSocket disconnected, retrying in 2s...');
    DOM.systemStatusText.textContent = 'Connection Lost';
    if (AppState.ws === ws) {
      AppState.ws = null;
    }
    setTimeout(() => {
      if (!AppState.ws) connectWebSocket();
    }, 2000);
  };

  AppState.ws = ws;
  return ws;
}

function setCameraMode(action, role = AppState.role) {
  const command = action ? { action, role } : { action: 'stop_camera' };
  AppState.cameraCommand = action ? command : null;
  const ws = connectWebSocket();
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(command));
  }
}

// ---------------------------------------------------------------------------
// WebSocket Message Dispatcher
// ---------------------------------------------------------------------------
function handleWebSocketMessage(msg) {
  // Update canvas if server sent annotated frame
  if (msg.image) {
    const activeCanvas = AppState.currentScreen === 'screen-face' ? DOM.cameraOverlay : DOM.regCanvasOverlay;
    if (activeCanvas) {
      const img = new Image();
      img.onload = () => {
        activeCanvas.width = img.width;
        activeCanvas.height = img.height;
        const ctx = activeCanvas.getContext('2d');
        ctx.drawImage(img, 0, 0);
      };
      img.src = msg.image;
    }
  }

  // Recognition Mode Messages
  if (AppState.currentScreen === 'screen-face') {
    if (msg.recognized) {
      handleRecognitionSuccess(msg.recognized);
    } else if (msg.fail_count !== undefined) {
      handleRecognitionFailure(msg.fail_count, msg.show_register);
    }
    if (msg.spoof_detected) {
      const score = Math.round((msg.liveness_score || 0) * 100);
      DOM.camDetectionStatus.textContent = `Spoof check failed (${score}% live confidence). Please use a live face.`;
    }
  }

  // Registration Mode Messages
  if (AppState.currentScreen === 'screen-register') {
    if (msg.reg_captured !== undefined) {
      DOM.regFramesCount.textContent = msg.reg_captured;
    }
    if (msg.quality !== undefined) {
      const pct = Math.round(msg.quality * 100);
      DOM.regQualityVal.textContent = `${pct}%`;
      DOM.regQualityBar.style.width = `${pct}%`;
    }
    if (msg.liveness_score !== undefined && msg.liveness_score !== null) {
      const pct = Math.round(msg.liveness_score * 100);
      DOM.regLivenessStatus.textContent = msg.spoof_detected
        ? `Anti-spoofing blocked this frame (${pct}% live confidence).`
        : `Live face confirmed (${pct}% confidence).`;
      DOM.regLivenessStatus.classList.toggle('is-spoof', Boolean(msg.spoof_detected));
      DOM.regLivenessStatus.classList.toggle('is-live', !msg.spoof_detected);
    } else if (msg.reg_captured !== undefined) {
      DOM.regLivenessStatus.textContent = 'No face detected. Center your face in the camera.';
      DOM.regLivenessStatus.classList.remove('is-spoof', 'is-live');
    }
    if (msg.duplicate) {
      DOM.duplicateAlert.classList.remove('hidden');
      DOM.duplicateAlertMsg.textContent = msg.duplicate.message || 'Face already registered in system!';
      DOM.regFramesCount.textContent = '0';
    }
    if (msg.registration_complete) {
      AppState.capturedEmbeddingHex = msg.embedding_hex;
      AppState.cameraCommand = null;
      enableRegistrationForm();
      showToast('Collected 5 valid live-face frames and passed anti-spoofing checks!', 'success');
    }
  }
}

// ---------------------------------------------------------------------------
// Face Recognition Handlers
// ---------------------------------------------------------------------------
function resetAttemptDots() {
  const dots = DOM.attemptDots.querySelectorAll('.dot');
  dots.forEach(d => d.classList.remove('failed'));
  DOM.attemptCountText.textContent = `0 / ${AppState.maxFailAttempts}`;
  AppState.failCount = 0;
}

function updateAttemptDots(count) {
  AppState.failCount = count;
  const dots = DOM.attemptDots.querySelectorAll('.dot');
  dots.forEach((d, idx) => {
    if (idx < count) {
      d.classList.add('failed');
    } else {
      d.classList.remove('failed');
    }
  });
  DOM.attemptCountText.textContent = `${count} / ${AppState.maxFailAttempts}`;
}

function handleRecognitionFailure(failCount, showRegister) {
  updateAttemptDots(failCount);
  DOM.camDetectionStatus.innerHTML = `<span class="dot-warn"></span> Authentication attempt failed (${failCount}/${AppState.maxFailAttempts})`;

  if (showRegister) {
    DOM.registerPromptBox.classList.remove('hidden');
    DOM.camDetectionStatus.innerHTML = `<span class="dot-warn" style="background:#f43f5e"></span> Max attempts exceeded (5/5)`;
  }
}

function handleRecognitionSuccess(user) {
  AppState.authenticatedUser = user;
  DOM.camDetectionStatus.innerHTML = `<span class="dot-warn" style="background:#10b981"></span> Verified: ${user.name}`;

  DOM.matchUserName.textContent = user.name;
  DOM.matchUserRole.textContent = `${user.role.toUpperCase()} • ${user.management_unit || 'Verified'}`;
  DOM.matchConfidence.textContent = `${Math.round(user.confidence * 100)}%`;
  DOM.matchPhone.textContent = user.phone_masked || '***';
  DOM.matchCard.classList.remove('hidden');
  DOM.registerPromptBox.classList.add('hidden');

  // Check if we are in mandatory re-authentication mode
  if (AppState.reauthMode) {
    showToast(`Re-authentication successful for ${user.name}! Proceeding to session...`, 'success');
    AppState.reauthMode = false;
    setTimeout(() => {
      proceedAfterAuthentication();
    }, 1200);
  }
}

function proceedAfterAuthentication() {
  if (!AppState.authenticatedUser) return;

  if (AppState.role === 'shipper') {
    // Continue to Receiver Selection screen
    loadReceiversScreen();
  } else if (AppState.role === 'receiver') {
    // Find assigned locker & check active deposited parcel
    checkReceiverActiveParcel(AppState.authenticatedUser.user_id);
  }
}

// ---------------------------------------------------------------------------
// Receiver Flow: Active Parcel Check
// ---------------------------------------------------------------------------
async function checkReceiverActiveParcel(receiverId) {
  try {
    const res = await fetch(`/api/receiver/${receiverId}/active_parcel`);
    const data = await res.json();

    if (!data.has_parcel) {
      alert(`Hello ${AppState.authenticatedUser.name}.\n${data.message || 'No deposited parcels found awaiting your pickup.'}`);
      showScreen('screen-start');
      return;
    }

    // Active deposited parcel found! Open collect screen and unlock locker
    AppState.activeTransaction = { id: data.transaction_id };
    AppState.currentLocker = { id: data.locker_id, number: data.locker_number };

    setupCollectScreen(data);
    showScreen('screen-collect');

    // Trigger API to open locker
    await fetch('/api/collect/open', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        receiver_id: receiverId,
        transaction_id: data.transaction_id,
      }),
    });
  } catch (err) {
    console.error('Error checking receiver parcel:', err);
    showToast('Error checking active parcels', 'error');
  }
}

function setupCollectScreen(data) {
  DOM.collectTargetLocker.textContent = data.locker_number;
  DOM.collectLockerPlate.textContent = data.locker_number;
  DOM.collectRecName.textContent = AppState.authenticatedUser.name;
  DOM.collectRecLocker.textContent = `Compartment ${data.locker_number}`;
  DOM.collectDepositedTime.textContent = data.deposited_at || 'Just deposited';
  DOM.collectShipperName.textContent = data.shipper_name || 'Shipper';

  // Door is open
  DOM.collectDoorGraphic.classList.add('opened');
  DOM.collectDoorStatusText.textContent = `🚪 COMPARTMENT ${data.locker_number} UNLOCKED • READY FOR COLLECTION`;
  DOM.collectDoorStatusText.className = 'deposit-status-badge open';
  DOM.collectLockerLed.className = 'locker-led-status open-pulse';

  DOM.collectCompleteCard.classList.add('hidden');
  DOM.collectReceipt.classList.add('hidden');
  DOM.collectSensorFlowBox.classList.remove('hidden');
}

// ---------------------------------------------------------------------------
// Shipper Flow: Receiver Selection & Deposit
// ---------------------------------------------------------------------------
let allReceivers = [];

async function loadReceiversScreen() {
  try {
    const res = await fetch('/api/receivers');
    allReceivers = await res.json();
    renderReceivers(allReceivers);
    showScreen('screen-receivers');
  } catch (err) {
    console.error('Error loading receivers:', err);
    showToast('Failed to load receivers directory', 'error');
  }
}

function renderReceivers(list) {
  DOM.receiversGrid.innerHTML = '';
  if (list.length === 0) {
    DOM.receiversGrid.innerHTML = '<p class="text-muted">No receivers registered in directory.</p>';
    return;
  }

  list.forEach(rec => {
    const card = document.createElement('div');
    card.className = 'receiver-card';
    card.innerHTML = `
      <div class="rec-card-top">
        <div class="rec-avatar">${rec.name.charAt(0)}</div>
        <span class="rec-tag-room">${rec.external_id || 'Unit'}</span>
      </div>
      <div>
        <h4 class="rec-name">${rec.name}</h4>
        <div class="rec-phone-masked">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"></path></svg>
          <span>${rec.phone_masked}</span>
        </div>
      </div>
      <div class="rec-unit">${rec.management_unit || 'Residential Tower'}</div>
    `;

    card.addEventListener('click', () => {
      onReceiverSelected(rec);
    });
    DOM.receiversGrid.appendChild(card);
  });
}

async function onReceiverSelected(receiver) {
  AppState.selectedReceiver = receiver;

  // Check whether locker assigned to this receiver is available
  try {
    const checkRes = await fetch('/api/deposit/check_locker', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ receiver_id: receiver.id }),
    });
    const checkData = await checkRes.json();

    if (!checkData.available) {
      alert('All locker compartments are currently occupied. Please try again later!');
      return;
    }

    // Open locker
    const openRes = await fetch('/api/deposit/open', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        shipper_id: AppState.authenticatedUser.user_id,
        receiver_id: receiver.id,
        locker_id: checkData.locker_id,
      }),
    });
    const openData = await openRes.json();

    if (openData.ok) {
      AppState.currentLocker = { id: checkData.locker_id, number: openData.locker_number };
      AppState.activeTransaction = { id: openData.transaction_id };

      setupDepositScreen(openData.locker_number, receiver);
      showScreen('screen-deposit');
    }
  } catch (err) {
    console.error('Error initiating deposit:', err);
    showToast('Failed to initialize deposit', 'error');
  }
}

function setupDepositScreen(lockerNumber, receiver) {
  DOM.depositTargetLocker.textContent = lockerNumber;
  DOM.depositLockerPlate.textContent = lockerNumber;
  DOM.depositRecName.textContent = receiver.name;
  DOM.depositRecPhone.textContent = receiver.phone_masked;
  DOM.depositRecUnit.textContent = `${receiver.management_unit} • ${receiver.external_id || ''}`;

  DOM.depositDoorGraphic.classList.add('opened');
  DOM.depositDoorStatusText.textContent = `🚪 COMPARTMENT ${lockerNumber} OPEN • READY FOR DEPOSIT`;
  DOM.depositDoorStatusText.className = 'deposit-status-badge open';
  DOM.depositLockerLed.className = 'locker-led-status open-pulse';

  DOM.depositCompleteCard.classList.add('hidden');
  DOM.depositReceipt.classList.add('hidden');
  DOM.btnSimulatePlaceParcel.disabled = false;
}

// ---------------------------------------------------------------------------
// Registration Screen Handlers
// ---------------------------------------------------------------------------
function enableRegistrationForm() {
  DOM.formRegisterUser.classList.remove('disabled-form');
  DOM.regInputName.disabled = false;
  DOM.regInputPhone.disabled = false;
  DOM.regInputUnit.disabled = false;
  DOM.regInputExtId.disabled = false;
  DOM.btnSubmitRegistration.disabled = false;

  // Customize label according to role
  if (AppState.role === 'shipper') {
    DOM.labelExtId.textContent = 'Shipper ID *';
    DOM.regInputExtId.placeholder = 'e.g. SHIP-8899';
    DOM.regRoleTag.textContent = 'SHIPPER REGISTRATION';
  } else {
    DOM.labelExtId.textContent = 'Apartment / Room ID *';
    DOM.regInputExtId.placeholder = 'e.g. Apt 1204 / REC-01';
    DOM.regRoleTag.textContent = 'RECEIVER REGISTRATION';
  }
}

function resetRegistrationScreen() {
  DOM.regFramesCount.textContent = '0';
  DOM.regQualityVal.textContent = '0%';
  DOM.regQualityBar.style.width = '0%';
  DOM.regLivenessStatus.textContent = 'Anti-spoofing check will appear when a face is detected.';
  DOM.regLivenessStatus.classList.remove('is-spoof', 'is-live');
  DOM.duplicateAlert.classList.add('hidden');
  DOM.formRegisterUser.reset();
  DOM.formRegisterUser.classList.add('disabled-form');
  DOM.regInputName.disabled = true;
  DOM.regInputPhone.disabled = true;
  DOM.regInputUnit.disabled = true;
  DOM.regInputExtId.disabled = true;
  DOM.btnSubmitRegistration.disabled = true;
  AppState.capturedEmbeddingHex = null;
}

async function handleRegisterSubmit(e) {
  e.preventDefault();
  if (!AppState.capturedEmbeddingHex) {
    showToast('Not enough valid face frames captured from camera!', 'error');
    return;
  }

  const payload = {
    name: DOM.regInputName.value.trim(),
    phone: DOM.regInputPhone.value.trim(),
    role: AppState.role,
    management_unit: DOM.regInputUnit.value.trim(),
    external_id: DOM.regInputExtId.value.trim(),
    embedding_hex: AppState.capturedEmbeddingHex,
  };

  try {
    const res = await fetch('/api/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (data.ok) {
      alert(`Face registered successfully for ${data.name}!\n\nPer security regulations, you are REQUIRED TO RE-AUTHENTICATE your face right now to activate your session.`);
      
      // Mandatory face re-authentication
      AppState.reauthMode = true;
      openFaceDetectionScreen(AppState.role, true);
    } else {
      showToast(data.detail || 'Registration failed', 'error');
    }
  } catch (err) {
    console.error('Registration error:', err);
    showToast('Could not connect to registration server', 'error');
  }
}

// ---------------------------------------------------------------------------
// Open Face Detection Screen
// ---------------------------------------------------------------------------
async function openFaceDetectionScreen(role, isReauth = false) {
  AppState.role = role;
  AppState.reauthMode = isReauth;
  resetAttemptDots();
  DOM.matchCard.classList.add('hidden');
  DOM.registerPromptBox.classList.add('hidden');
  DOM.camDetectionStatus.innerHTML = '<span class="dot-warn"></span> Initializing AI Camera...';

  DOM.currentRoleTag.textContent = role.toUpperCase();
  if (isReauth) {
    DOM.faceModeTitle.textContent = 'Face Re-Authentication (Mandatory)';
    DOM.faceModeDesc.textContent = 'Registration complete! Please look at the camera to verify your identity and activate your session.';
  } else {
    DOM.faceModeTitle.textContent = role === 'shipper' ? 'Shipper Face Authentication' : 'Receiver Face Authentication';
    DOM.faceModeDesc.textContent = 'Please look directly at the camera. If authentication fails 5 consecutive times, registration will appear.';
  }

  showScreen('screen-face');

  // Stream directly from Edge Camera Service
  setCameraMode('start_recognition', role);
}

// ---------------------------------------------------------------------------
// Event Listeners
// ---------------------------------------------------------------------------
function setupEventListeners() {
  // Start Screen -> Role
  DOM.btnStart.addEventListener('click', () => {
    showScreen('screen-role');
  });

  DOM.btnBackToStart.addEventListener('click', () => {
    showScreen('screen-start');
  });

  // Role Screen -> Face Detection
  DOM.cardRoleShipper.addEventListener('click', () => {
    openFaceDetectionScreen('shipper', false);
  });

  DOM.cardRoleReceiver.addEventListener('click', () => {
    openFaceDetectionScreen('receiver', false);
  });

  DOM.btnCancelFace.addEventListener('click', () => {
    setCameraMode(null);
    showScreen('screen-role');
  });

  DOM.btnConfirmMatch.addEventListener('click', () => {
    proceedAfterAuthentication();
  });

  // Trigger Registration Screen
  DOM.btnTriggerRegister.addEventListener('click', () => {
    resetRegistrationScreen();
    showScreen('screen-register');

    setCameraMode('start_registration');
  });

  DOM.btnCancelRegistration.addEventListener('click', () => {
    setCameraMode(null);
    showScreen('screen-role');
  });

  DOM.formRegisterUser.addEventListener('submit', handleRegisterSubmit);

  // Receiver Search
  DOM.inputSearchReceiver.addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase().trim();
    const filtered = allReceivers.filter(r => r.name.toLowerCase().includes(q));
    renderReceivers(filtered);
  });

  DOM.btnBackFromReceivers.addEventListener('click', () => {
    showScreen('screen-face');
  });

  // Shipper Deposit: Simulate Sensor Placement
  DOM.btnSimulatePlaceParcel.addEventListener('click', async () => {
    DOM.btnSimulatePlaceParcel.disabled = true;
    try {
      const res = await fetch('/api/deposit/sensor_detect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ locker_number: AppState.currentLocker.number }),
      });
      const data = await res.json();

      if (data.parcel_detected) {
        DOM.depositCompleteCard.classList.remove('hidden');

        // Countdown and close door
        let count = 3;
        DOM.depositCountdown.textContent = count;
        const timer = setInterval(async () => {
          count--;
          DOM.depositCountdown.textContent = count;
          if (count <= 0) {
            clearInterval(timer);
            // Close locker & complete deposit
            DOM.depositDoorGraphic.classList.remove('opened');
            DOM.depositDoorStatusText.textContent = `🔒 COMPARTMENT ${AppState.currentLocker.number} CLOSED & LOCKED`;
            DOM.depositDoorStatusText.className = 'deposit-status-badge';
            DOM.depositLockerLed.className = 'locker-led-status';

            const compRes = await fetch('/api/deposit/complete', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                transaction_id: AppState.activeTransaction.id,
                locker_number: AppState.currentLocker.number,
              }),
            });
            const compData = await compRes.json();

            DOM.depositCompleteCard.classList.add('hidden');
            DOM.depositReceipt.classList.remove('hidden');
            DOM.receiptTxId.textContent = `#TX-${compData.transaction_id}`;
            DOM.receiptLocker.textContent = compData.locker_number;
            DOM.receiptTime.textContent = compData.deposited_at || new Date().toLocaleString();
          }
        }, 1000);
      }
    } catch (err) {
      console.error('Sensor detection error:', err);
    }
  });

  DOM.btnFinishDeposit.addEventListener('click', () => {
    setCameraMode(null);
    showScreen('screen-start');
    showToast('Parcel deposit transaction successfully completed!', 'success');
  });

  // Receiver Collect: Simulate Sensor Removal
  DOM.btnSimulateRemoveParcel.addEventListener('click', async () => {
    DOM.btnSimulateRemoveParcel.disabled = true;
    try {
      const res = await fetch('/api/collect/sensor_detect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ locker_number: AppState.currentLocker.number }),
      });
      const data = await res.json();

      if (data.parcel_removed) {
        DOM.collectSensorFlowBox.classList.add('hidden');
        DOM.collectCompleteCard.classList.remove('hidden');

        let count = 3;
        DOM.collectCountdown.textContent = count;
        const timer = setInterval(async () => {
          count--;
          DOM.collectCountdown.textContent = count;
          if (count <= 0) {
            clearInterval(timer);
            // Close locker & complete collect
            DOM.collectDoorGraphic.classList.remove('opened');
            DOM.collectDoorStatusText.textContent = `🔒 COMPARTMENT ${AppState.currentLocker.number} CLOSED & LOCKED`;
            DOM.collectDoorStatusText.className = 'deposit-status-badge';
            DOM.collectLockerLed.className = 'locker-led-status';

            const compRes = await fetch('/api/collect/complete', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                receiver_id: AppState.authenticatedUser.user_id,
                transaction_id: AppState.activeTransaction.id,
                locker_number: AppState.currentLocker.number,
              }),
            });
            const compData = await compRes.json();

            DOM.collectCompleteCard.classList.add('hidden');
            DOM.collectReceipt.classList.remove('hidden');
            DOM.collectReceiptLocker.textContent = compData.locker_number;
            DOM.collectReceiptTime.textContent = compData.collected_at || new Date().toLocaleString();
          }
        }, 1000);
      }
    } catch (err) {
      console.error('Sensor removal error:', err);
    }
  });

  DOM.btnFinishCollect.addEventListener('click', () => {
    setCameraMode(null);
    showScreen('screen-start');
    showToast('Parcel collection completed successfully!', 'success');
  });

  // Hardware Modal
  DOM.btnToggleHardware.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/lockers');
      const lockers = await res.json();
      DOM.lockersGridPreview.innerHTML = '';
      lockers.forEach(l => {
        const cell = document.createElement('div');
        cell.className = `locker-cell ${l.status === 'occupied' ? 'occupied' : ''}`;
        cell.innerHTML = `
          <div class="locker-cell-num">${l.number}</div>
          <span class="locker-badge ${l.status === 'available' ? 'badge-avail' : 'badge-occ'}">
            ${l.status === 'available' ? 'Available' : 'Occupied'}
          </span>
          <small class="text-dim">${l.locked ? '🔒 Locked' : '🔓 Unlocked'}</small>
          ${l.assigned_receiver ? `<small class="text-dim">Resident: ${l.assigned_receiver}</small>` : ''}
        `;
        DOM.lockersGridPreview.appendChild(cell);
      });
      DOM.modalHardware.classList.remove('hidden');
    } catch (e) {
      console.error(e);
    }
  });

  DOM.btnCloseHardware.addEventListener('click', () => {
    DOM.modalHardware.classList.add('hidden');
  });

  // Audit Log Modal
  DOM.btnToggleAudit.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/audit-logs');
      const logs = await res.json();
      DOM.auditTableBody.innerHTML = '';
      logs.forEach(log => {
        const row = document.createElement('tr');
        row.innerHTML = `
          <td>${log.timestamp}</td>
          <td>${log.user_id || '-'}</td>
          <td><strong>${log.role || '-'}</strong></td>
          <td>${log.receiver_id || '-'}</td>
          <td>${log.locker_id ? `Locker #${log.locker_id}` : '-'}</td>
          <td><span class="${log.auth_result === 'success' ? 'text-success' : ''}">${log.auth_result || '-'}</span></td>
          <td>${log.parcel_status || '-'}</td>
          <td>${log.action || '-'}</td>
        `;
        DOM.auditTableBody.appendChild(row);
      });
      DOM.modalAudit.classList.remove('hidden');
    } catch (e) {
      console.error(e);
    }
  });

  DOM.btnCloseAudit.addEventListener('click', () => {
    DOM.modalAudit.classList.add('hidden');
  });
}

// Init
window.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  connectWebSocket();
});
