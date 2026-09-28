/* =========================================================
   FlowMind 사용 허가 (무료 체험 / 정품 인증)

   - 무료: 처음 실행한 시각부터 24시간까지만 동작
   - 정품: 이 PC의 기기 코드로 발급된 16자 인증키를 넣으면 기간 제한 없음
   - 인증키는 기기 코드에서 나오므로 다른 PC에서는 통하지 않는다.
     매 실행마다 다시 검사하므로 인증 파일을 복사해 와도 소용없다.
   - 상태는 localStorage 와 (Electron이면) 사용자 폴더의 파일 두 곳에 함께 남긴다.
     한쪽을 지워도 다른 쪽에서 되살아난다.

   주의: 검사는 프로그램 안에서만 이루어진다. 서버 확인이 없으므로
   마음먹고 뜯어보는 사람까지 막지는 못한다. 일반 사용자를 대상으로 한 장치다.
   ========================================================= */
'use strict';

const LICENSE = (function () {
  const TRIAL_MS = 24 * 60 * 60 * 1000;      // 무료 사용 기간: 24시간
  const LS_KEY = 'flowmind:lic';
  const CLOCK_SLACK_MS = 60 * 1000;          // 시계 오차 허용치

  const b = window.flowmind || null;

  function normalize(input) {
    return String(input || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  }

  function merge(a, c) {
    if (!a) return c;
    if (!c) return a;
    return {
      // 먼저 기록된 실행 시각을 채택해야 지웠다 다시 깔아도 기간이 늘어나지 않는다
      firstRun: Math.min(a.firstRun || Infinity, c.firstRun || Infinity),
      lastSeen: Math.max(a.lastSeen || 0, c.lastSeen || 0),
      activated: !!(a.activated || c.activated),
      serial: a.serial || c.serial || null,
      machine: a.machine || c.machine || null,
      tampered: !!(a.tampered || c.tampered)
    };
  }

  /* 이 PC의 기기 코드. Electron에서는 메인보드 정보로 만든다. */
  let cachedMid = null;
  async function machineIdOf() {
    if (cachedMid) return cachedMid;
    if (b && b.machineId) {
      try { cachedMid = await b.machineId(); } catch (e) { /* 무시 */ }
    }
    if (!cachedMid) {
      // 브라우저에서는 하드웨어를 읽을 수 없어 이 브라우저 전용 임의 값으로 대신한다
      try {
        cachedMid = localStorage.getItem('flowmind:mid');
        if (!cachedMid) {
          const a = new Uint8Array(8);
          crypto.getRandomValues(a);
          cachedMid = 'B' + Array.from(a).map((x) => x.toString(16).padStart(2, '0')).join('').toUpperCase().slice(0, 15);
          localStorage.setItem('flowmind:mid', cachedMid);
        }
      } catch (e) { cachedMid = 'UNKNOWN0000000'; }
    }
    return cachedMid;
  }

  async function readState() {
    let fromFile = null;
    if (b && b.licenseRead) {
      try { fromFile = await b.licenseRead(); } catch (e) { /* 무시 */ }
    }
    let fromLs = null;
    try { fromLs = JSON.parse(localStorage.getItem(LS_KEY) || 'null'); } catch (e) { /* 무시 */ }
    const s = merge(fromFile, fromLs);
    return (s && isFinite(s.firstRun)) ? s : null;
  }

  async function writeState(s) {
    try { localStorage.setItem(LS_KEY, JSON.stringify(s)); } catch (e) { /* 무시 */ }
    if (b && b.licenseWrite) {
      try { await b.licenseWrite(s); } catch (e) { /* 무시 */ }
    }
  }

  /** 현재 사용 가능 여부 */
  async function status() {
    const now = Date.now();
    let s = await readState();
    if (!s) s = { firstRun: now, lastSeen: now, activated: false, serial: null, tampered: false };

    // 시계를 과거로 돌린 흔적이 있으면 체험 기간을 즉시 끝낸다
    if (s.lastSeen && now < s.lastSeen - CLOCK_SLACK_MS) s.tampered = true;
    s.lastSeen = Math.max(s.lastSeen || 0, now);
    await writeState(s);

    const mid = await machineIdOf();

    if (s.activated) {
      // 인증키를 매번 이 PC의 기기 코드로 다시 검사한다.
      // 인증 파일을 통째로 복사해 와도 키가 맞지 않아 통과하지 못한다.
      if (b && b.licenseVerify && s.serial) {
        const v = await b.licenseVerify(s.serial);
        if (!v.ok) {
          return {
            activated: false, expired: true, wrongMachine: true,
            boundTo: s.machine, machine: mid, serial: s.serial, trialMs: TRIAL_MS
          };
        }
      }
      if (!s.machine) {
        s.machine = mid;
        await writeState(s);
      }
      if (s.machine !== mid) {
        // 인증 정보를 다른 PC로 옮겨온 경우
        return {
          activated: false, expired: true, wrongMachine: true,
          boundTo: s.machine, machine: mid, serial: s.serial, trialMs: TRIAL_MS
        };
      }
      return { activated: true, expired: false, serial: s.serial, machine: mid, trialMs: TRIAL_MS };
    }

    const msLeft = s.tampered ? 0 : Math.max(0, s.firstRun + TRIAL_MS - now);
    return {
      activated: false,
      expired: msLeft <= 0,
      msLeft: msLeft,
      tampered: !!s.tampered,
      machine: mid,
      trialMs: TRIAL_MS
    };
  }

  /** 이 PC용으로 발급된 인증키인지 확인하고 인증 처리 */
  async function activate(input) {
    const serial = normalize(input);
    if (serial.length !== 16) {
      return { ok: false, reason: '인증키는 16자입니다. (' + serial.length + '자 입력됨)' };
    }
    if (!(b && b.licenseVerify)) {
      return { ok: false, reason: '설치된 FlowMind 프로그램에서만 인증할 수 있습니다.' };
    }
    const v = await b.licenseVerify(serial);
    if (!v.ok) return v;

    const s = (await readState()) || { firstRun: Date.now() };
    s.activated = true;
    s.serial = serial;
    s.machine = await machineIdOf();       // 이 메인보드에 묶는다
    s.tampered = false;
    s.lastSeen = Date.now();
    await writeState(s);
    return { ok: true, serial: serial, machine: s.machine };
  }

  /** 고객이 불러주기 좋게 4자씩 끊은 기기 코드 */
  async function machineCode() {
    return (await machineIdOf()).replace(/(.{4})(?=.)/g, '$1-');
  }

  /** 남은 시간을 사람이 읽는 형태로 */
  function formatLeft(ms) {
    if (ms <= 0) return '만료됨';
    const h = Math.floor(ms / 3600000);
    const m = Math.floor((ms % 3600000) / 60000);
    if (h > 0) return h + '시간 ' + m + '분';
    if (m > 0) return m + '분';
    return Math.max(1, Math.floor(ms / 1000)) + '초';
  }

  /** 화면에 보여줄 때만 가운데를 가린다 */
  function mask(serial) {
    const s = normalize(serial);
    if (s.length !== 16) return s;
    return s.slice(0, 4) + '-****-****-' + s.slice(12);
  }

  function group(serial) {
    return normalize(serial).replace(/(.{4})(?=.)/g, '$1-');
  }

  return { status, activate, formatLeft, mask, group, normalize, machineCode, TRIAL_MS };
})();
