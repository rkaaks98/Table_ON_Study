const menuName = {
    '0': { display: '', tts: '' },
    '1': { display: '허니자몽\n블랙티\n(HOT)', tts: '따뜻한 허니자몽블랙티' },
    '3': { display: '아메리카노\n(HOT)', tts: '따뜻한 아메리카노' },
    '4': { display: '아메리카노\n(ICE)', tts: '아이스 아메리카노' },
    '5': { display: '카페라떼\n(HOT)', tts: '따뜻한 카페라떼' },
    '6': { display: '카페라떼\n(ICE)', tts: '아이스 카페라떼' },
    '7': { display: '바닐라라떼\n(HOT)', tts: '따뜻한 바닐라라떼' },
    '8': { display: '바닐라라떼\n(ICE)', tts: '아이스 바닐라라떼' },
    '9': { display: '카라멜\n마끼아또\n(HOT)', tts: '따뜻한 카라멜마끼아또' },
    '10': { display: '카라멜\n마끼아또\n(ICE)', tts: '아이스 카라멜마끼아또' },
    '11': { display: '초당옥수수\n샷 라떼(HOT)', tts: '따뜻한 초당옥수수 샷 라떼' },
    '12': { display: '초당옥수수\n샷 라떼(ICE)', tts: '아이스 초당옥수수 샷 라떼' },
    '13': { display: '레몬티\n(HOT)', tts: '따뜻한 레몬티' },
    '14': { display: '레몬에이드', tts: '레몬에이드' },
    '15': { display: '자몽티\n(HOT)', tts: '따뜻한 자몽티' },
    '16': { display: '자몽에이드', tts: '자몽에이드' },
    '17': { display: '허니자몽 블랙티', tts: '허니자몽 블랙티' },
    '55': { display: '샷 추출\n(Co-op)', tts: '샷 추출' }
};

// --- BGM 설정 ---
//const bgmFiles = Array.from({length: 16}, (_, i) => `/static/sound/bgm_${i + 1}.mp3`);
//let lastBgmIndex = -1;

// --- TTS (음성 안내) 설정 ---
const ttsQueue = [];
let isSpeaking = false;
let currentPickupState = {}; // 현재 픽업대 상태를 저장할 변수
let preferredVoice = null; // 선호하는 목소리를 저장할 변수
let hasPickupSnapshot = false; // 초기 상태가 세팅되었는지 여부

const BILLNUM_OFFSET = 0;
const toInt = v => {
  const n = parseInt(v, 10);
  return Number.isFinite(n) ? n : 0;
};
const fmtBill = v => {
  const n = toInt(v);
  // 주문번호가 999면 오프셋 적용하지 않음
  if (n === 0 || n === 999) return numLen(n);
  return numLen(n - BILLNUM_OFFSET);
};

/**
 * 사용 가능한 음성 목록에서 최적의 한국어 음성을 찾아 설정합니다.
 */
function setTtsVoice() {
    const voices = window.speechSynthesis.getVoices();
    console.log("사용 가능한 음성 목록:", voices);

    // 선호하는 목소리 이름 목록 (우선순위 순)
    const preferredVoiceNames = [
        'Microsoft Heami Online', // Windows 11 고품질 온라인 음성
        'Google 한국의',          // Google Chrome 제공 음성
        'Microsoft Heami'         // Windows 10 기본 음성
    ];

    for (const name of preferredVoiceNames) {
        const foundVoice = voices.find(voice => voice.name.includes(name) && voice.lang === 'ko-KR');
        if (foundVoice) {
            preferredVoice = foundVoice;
            break; // 가장 우선순위 높은 목소리를 찾으면 중단
        }
    }

    // 선호하는 목소리를 못 찾았을 경우, 첫 번째 한국어 목소리 사용
    if (!preferredVoice) {
        preferredVoice = voices.find(voice => voice.lang === 'ko-KR');
    }

    if (preferredVoice) {
        console.log("선택된 음성:", preferredVoice);
    } else {
        console.warn("사용 가능한 한국어 음성을 찾을 수 없습니다.");
    }
}

/**
 * 숫자를 3자리 주문번호 형식의 문자열로 변환합니다. (예: 7 -> "007")
 * @param {number} number - 주문번호
 * @returns {string} 포맷팅된 주문번호 문자열
 */
function numLen(number) {
    if (!number || number === 0) {
        return '';
    }
    return String(number).padStart(3, '0');
}

/**
 * 픽업대 UI를 업데이트하는 함수
 * @param {object} data - 픽업대 상태 데이터
 */
function updatePickupSlots(data) {
    currentPickupState = data; // 상태 정보 업데이트
    document.getElementById('pick-up_1').textContent = menuName[data.menuCode01]?.display || '';
    document.getElementById('pick-up_2').textContent = menuName[data.menuCode02]?.display || '';
    document.getElementById('pick-up_3').textContent = menuName[data.menuCode03]?.display || '';
    document.getElementById('pick-up_4').textContent = menuName[data.menuCode04]?.display || '';

    document.getElementById('order_code_1').textContent = fmtBill(data.billNum01);
    document.getElementById('order_code_2').textContent = fmtBill(data.billNum02);
    document.getElementById('order_code_3').textContent = fmtBill(data.billNum03);
    document.getElementById('order_code_4').textContent = fmtBill(data.billNum04);
}

/**
 * BGM을 랜덤으로 재생하는 함수
 */
function playRandomBgm() {
    const bgmPlayer = document.getElementById('bgm-player');
    if (!bgmPlayer) return;

    let randomIndex;
    // 이전에 재생한 곡과 다른 곡을 선택
    do {
        randomIndex = Math.floor(Math.random() * bgmFiles.length);
    } while (bgmFiles.length > 1 && randomIndex === lastBgmIndex);
    
    lastBgmIndex = randomIndex;
    bgmPlayer.src = bgmFiles[randomIndex];
    bgmPlayer.volume = 0.7; // BGM 볼륨 설정 (0.0 ~ 1.0)

    // 플레이어를 리셋하고 새 소스를 강제로 다시 로드합니다.
    // 이렇게 하면 이전 곡의 오류 상태가 다음 곡에 영향을 주지 않습니다.
    bgmPlayer.load();

    // 브라우저의 자동 재생 정책으로 인해 사용자의 상호작용이 있어야 재생될 수 있음
    const playPromise = bgmPlayer.play();
    if (playPromise !== undefined) {
        playPromise.catch(error => {
            console.warn('BGM 자동 재생이 차단되었습니다. 페이지와 상호작용 후 다시 시도됩니다.', error);
            // 사용자의 첫 클릭 시 BGM 재생을 시도하는 이벤트 리스너 추가
            document.body.addEventListener('click', () => bgmPlayer.play(), { once: true });
        });
    }
}

function playBgm() {
    const bgmPlayer = document.getElementById('bgm-player');
    if (!bgmPlayer) return;

    // 이전에 설정된 이벤트 리스너를 제거하여 중복 등록을 방지합니다.
    bgmPlayer.removeEventListener('ended', playBgm);
    bgmPlayer.removeEventListener('error', handleBgmError);

    // 단일 BGM 파일 경로 설정
    bgmPlayer.src = '/static/sound/bgm_replay.mp3';
    bgmPlayer.volume = 0.7;

    // 플레이어를 리셋하고 새 소스를 강제로 다시 로드합니다.
    bgmPlayer.load();

    // 브라우저의 자동 재생 정책 처리
    const playPromise = bgmPlayer.play();
    if (playPromise !== undefined) {
        playPromise.then(() => {
            // 재생이 성공적으로 시작되면, 끝났을 때와 에러 발생 시를 대비합니다.
            bgmPlayer.addEventListener('ended', playBgm, { once: true });
            bgmPlayer.addEventListener('error', handleBgmError, { once: true });
        }).catch(error => {
            console.warn('BGM 자동 재생이 차단되었습니다. 페이지와 상호작용 후 다시 시도됩니다.', error);
            // 사용자의 첫 클릭 시 BGM 재생을 시도하는 이벤트 리스너 추가
            document.body.addEventListener('click', playBgm, { once: true });
        });
    }
}
function handleBgmError(e) {
    console.error('BGM 재생 오류 발생:', e);
    // 10초 후에 재생을 다시 시도합니다.
    setTimeout(playBgm, 10000);
}

/**
 * TTS 큐를 처리하여 순서대로 음성을 재생하는 함수
 */
function processTtsQueue() {
    if (isSpeaking || ttsQueue.length === 0) {
        return;
    }
    isSpeaking = true;
    const text = ttsQueue.shift();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'ko-KR';
    utterance.rate = 1.0; // 목소리 속도
    utterance.pitch = 1.0; // 목소리 톤

    // 최적의 목소리를 찾았다면 설정
    if (preferredVoice) {
        utterance.voice = preferredVoice;
    }

    utterance.onend = function() {
        isSpeaking = false;
        setTimeout(processTtsQueue, 1000); // 다음 안내까지 약간의 딜레이
    };
    
    utterance.onerror = function(event) {
        console.error('TTS 재생 중 오류 발생:', event.error);
        isSpeaking = false;
        processTtsQueue(); // 오류 발생 시 다음 큐 처리
    };

    window.speechSynthesis.speak(utterance);
}

/**
 * 방금 새로 추가된 음료만 즉시 안내 멘트를 생성하는 함수
 * @param {object|null} oldState - 이전 픽업대 상태 (없을 수 있음)
 * @param {object} newState - 현재 픽업대 상태
 */
function announceNewItems(oldState, newState) {
    if (!newState || !oldState) {
        return;
    }

    let newItemsFound = false;
    for (let i = 1; i <= 4; i++) {
        const oldBillNumRaw = oldState[`billNum0${i}`];
        const newBillNumRaw = newState[`billNum0${i}`];
        const newMenuCode = newState[`menuCode0${i}`];

        const oldBillNum = oldBillNumRaw ? String(oldBillNumRaw) : '0';
        const newBillNum = newBillNumRaw ? String(newBillNumRaw) : '0';

        // 이전에는 비어있었거나 다른 주문이었는데, 지금은 새로운 주문으로 채워진 경우에만 안내
        if (newBillNum !== '0' && newBillNum !== oldBillNum && newMenuCode && newMenuCode !== '0') {
            const menuInfo = menuName[newMenuCode];
            if (!menuInfo) continue;

            const message = `${fmtBill(newBillNum)}번 주문, ${menuInfo.tts} 나왔습니다. ${i}번 픽업대에서 가져가 주세요.`;
            if (!ttsQueue.includes(message)) {
                ttsQueue.push(message);
                newItemsFound = true;
            }
        }
    }

    if (newItemsFound) {
        processTtsQueue();
    }
}

/**
 * 주기적으로 픽업대 상태를 확인하고 안내 멘트를 생성하는 함수
 */
function checkForAnnouncements() {
    if (!currentPickupState || isSpeaking) {
        return; // 데이터가 없거나 이미 말하는 중이면 실행하지 않음
    }

    for (let i = 1; i <= 4; i++) {
        const menuCode = currentPickupState[`menuCode0${i}`];
        const billNum = currentPickupState[`billNum0${i}`];

        if (menuCode && menuCode !== '0' && billNum && billNum !== 0) {
            const menuInfo = menuName[menuCode];
            if (!menuInfo) continue; // 메뉴 정보가 없으면 건너뜀

            const message = `${fmtBill(billNum)}번 주문, ${menuInfo.tts} 나왔습니다. ${i}번 픽업대에서 가져가 주세요.`;
            
            // 동일한 안내가 큐에 없으면 추가
            if (!ttsQueue.includes(message)) {
                ttsQueue.push(message);
            }
        }
    }
    processTtsQueue();
}

/**
 * 서버에서 픽업대 데이터를 폴링하는 함수
 */
function pollPickupData() {
    const PICKUP_SERVICE_URL = `http://${window.location.hostname}:8600`;
    
    axios.get(`${PICKUP_SERVICE_URL}/getDIDData`)
        .then(response => {
            console.log('폴링 데이터 수신:', response.data);
            
            const previousState = hasPickupSnapshot ? { ...currentPickupState } : null;
            updatePickupSlots(response.data);

            if (hasPickupSnapshot) {
                announceNewItems(previousState, currentPickupState);
            } else {
                hasPickupSnapshot = true;
            }
        })
        .catch(error => {
            console.error('픽업대 데이터 폴링 실패:', error);
        });
}

window.onload = function () {
    const PICKUP_SERVICE_URL = `http://${window.location.hostname}:8600`;

    // 1. 초기 데이터 로드
    axios.get(`${PICKUP_SERVICE_URL}/getDIDData`)
        .then(response => {
            updatePickupSlots(response.data);
            hasPickupSnapshot = true;
        })
        .catch(error => {
            console.error('초기 데이터 로드 실패:', error);
        });

    // 2. 실시간 데이터 업데이트 (폴링 방식으로 변경)
    // 2초마다 서버에서 데이터를 가져옴
    setInterval(pollPickupData, 1000);

    // 3. TTS 음성 설정
    // getVoices()는 비동기로 작동하므로, voiceschanged 이벤트를 수신하여 처리
    if (speechSynthesis.onvoiceschanged !== undefined) {
        speechSynthesis.onvoiceschanged = setTtsVoice;
    }
    setTtsVoice(); // 초기 로드 시도

    // 4. BGM 재생 시작
    const bgmPlayer = document.getElementById('bgm-player');
    if (bgmPlayer) {
        playBgm();
        //playRandomBgm();
        // 한 곡 재생이 끝나면 다음 곡 랜덤 재생
        //bgmPlayer.addEventListener('ended', playRandomBgm);
    }

    // 5. 주기적인 음성 안내 시작 (30초마다)
    setInterval(checkForAnnouncements, 30000);
};