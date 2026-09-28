const { app, BrowserWindow, ipcMain, dialog, Menu, shell } = require('electron');
const path = require('path');
const fs = require('fs/promises');
const os = require('os');
const crypto = require('crypto');
const { execFile } = require('child_process');

let win = null;

function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#14161c',
    title: 'FlowMind',
    icon: path.join(__dirname, 'build', 'icon.ico'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  Menu.setApplicationMenu(null); // 단축키는 앱 안에서 직접 처리
  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  // Ctrl + 휠 로 창 전체가 확대되지 않게 한다 (확대·축소는 앱이 직접 처리)
  win.webContents.setVisualZoomLevelLimits(1, 1);

  win.webContents.on('before-input-event', (event, input) => {
    if (input.type !== 'keyDown') return;
    // F12로 개발자 도구 토글
    if (input.key === 'F12') {
      win.webContents.toggleDevTools();
      event.preventDefault();
      return;
    }
    // Ctrl + = 는 노드 추가 단축키다. 크로미움 기본 확대가 끼어들면 되돌린다.
    if (input.control && (input.key === '=' || input.key === '+' || input.key === '-')) {
      win.webContents.setZoomLevel(0);
    }
  });

  // 외부 링크는 기본 브라우저로
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
}

app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

ipcMain.handle('file:save', async (_e, json, suggestedName) => {
  const { canceled, filePath } = await dialog.showSaveDialog(win, {
    title: '마인드맵 저장',
    defaultPath: suggestedName || 'mindmap.json',
    filters: [{ name: 'FlowMind 파일', extensions: ['json'] }],
  });
  if (canceled || !filePath) return { ok: false };
  await fs.writeFile(filePath, json, 'utf8');
  return { ok: true, path: filePath, name: path.basename(filePath) };
});

ipcMain.handle('file:open', async () => {
  const { canceled, filePaths } = await dialog.showOpenDialog(win, {
    title: '마인드맵 열기',
    properties: ['openFile'],
    filters: [{ name: 'FlowMind 파일', extensions: ['json'] }],
  });
  if (canceled || !filePaths.length) return { ok: false };
  const data = await fs.readFile(filePaths[0], 'utf8');
  return { ok: true, path: filePaths[0], name: path.basename(filePaths[0]), data };
});

/* ---------- 기기 식별 (메인보드 기준) ----------
   SMBIOS UUID와 메인보드 일련번호를 합쳐 해시한다. 둘 다 못 읽는 보드에서는
   호스트명·CPU·메모리로 대체한다. 메인보드를 갈면 값이 바뀐다. */
let cachedMachineId = null;

function psQuery(script) {
  return new Promise((resolve) => {
    execFile(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
      { timeout: 8000, windowsHide: true },
      (err, stdout) => resolve(err ? '' : String(stdout).trim())
    );
  });
}

function looksBlank(v) {
  return !v || /^(none|null|default string|to be filled by o\.?e\.?m\.?|system serial number|0+|-+)$/i.test(v.trim());
}

async function machineId() {
  if (cachedMachineId) return cachedMachineId;
  const parts = [];

  const uuid = await psQuery('(Get-CimInstance Win32_ComputerSystemProduct).UUID');
  const uuidBad = looksBlank(uuid) ||
    /^(0{8}-0{4}-0{4}-0{4}-0{12}|F{8}-F{4}-F{4}-F{4}-F{12})$/i.test(uuid.trim());
  if (!uuidBad) parts.push('U:' + uuid.trim().toUpperCase());

  const board = await psQuery('(Get-CimInstance Win32_BaseBoard).SerialNumber');
  if (!looksBlank(board)) parts.push('B:' + board.trim());

  if (!parts.length) {
    // 메인보드 정보를 못 읽는 PC를 위한 최후 수단
    const cpu = (os.cpus()[0] || {}).model || '';
    parts.push('H:' + os.hostname() + '|' + cpu + '|' + os.totalmem());
  }

  cachedMachineId = crypto.createHash('sha256')
    .update(parts.join('#')).digest('hex').slice(0, 16).toUpperCase();
  return cachedMachineId;
}

ipcMain.handle('machine:id', () => machineId());

/* ---------- 인증키 검사 ----------
   인증키는 이 PC의 기기 코드로만 만들 수 있으므로, 다른 PC에서 받은 키는 통과하지 못한다. */
const { keyForMachine, normalizeCode } = require('./license-core');

ipcMain.handle('license:verify', async (_e, input) => {
  const key = normalizeCode(input);
  if (key.length !== 16) {
    return { ok: false, reason: '인증키는 16자입니다. (' + key.length + '자 입력됨)' };
  }
  const mid = await machineId();
  const expected = keyForMachine(mid);
  const a = Buffer.from(key, 'utf8');
  const b = Buffer.from(expected, 'utf8');
  const ok = a.length === b.length && crypto.timingSafeEqual(a, b);
  return ok
    ? { ok: true, machine: mid }
    : { ok: false, reason: '이 PC의 기기 코드로 발급된 인증키가 아닙니다.' };
});

/* ---------- 사용 허가 상태 보관 ----------
   두 곳에 같이 적는다. 한쪽을 지워도 다른 쪽에서 되살아나 체험 기간이 초기화되지 않는다. */
function licensePaths() {
  return [
    path.join(app.getPath('userData'), 'license.json'),
    path.join(app.getPath('home'), '.flowmind-license'),
  ];
}

ipcMain.handle('license:read', async () => {
  let merged = null;
  for (const p of licensePaths()) {
    try {
      // 다른 도구가 BOM을 붙여 저장했더라도 읽히도록 앞머리를 걷어낸다
      const s = JSON.parse((await fs.readFile(p, 'utf8')).replace(/^﻿/, ''));
      if (!s || typeof s !== 'object') continue;
      merged = merged ? {
        firstRun: Math.min(merged.firstRun || Infinity, s.firstRun || Infinity),
        lastSeen: Math.max(merged.lastSeen || 0, s.lastSeen || 0),
        activated: !!(merged.activated || s.activated),
        serial: merged.serial || s.serial || null,
        machine: merged.machine || s.machine || null,
        tampered: !!(merged.tampered || s.tampered),
      } : s;
    } catch (e) { /* 파일이 없거나 깨졌으면 건너뛴다 */ }
  }
  return merged;
});

ipcMain.handle('license:write', async (_e, state) => {
  const json = JSON.stringify(state);
  for (const p of licensePaths()) {
    try {
      await fs.mkdir(path.dirname(p), { recursive: true });
      await fs.writeFile(p, json, 'utf8');
    } catch (e) { /* 한 곳만 성공해도 된다 */ }
  }
  return true;
});

const TEXT_FILTERS = {
  csv: [{ name: 'CSV (Excel)', extensions: ['csv'] }],
};

ipcMain.handle('file:saveText', async (_e, text, suggestedName, kind) => {
  const { canceled, filePath } = await dialog.showSaveDialog(win, {
    title: '내보내기',
    defaultPath: suggestedName || 'export.csv',
    filters: TEXT_FILTERS[kind] || [],
  });
  if (canceled || !filePath) return { ok: false };
  await fs.writeFile(filePath, text, 'utf8');
  return { ok: true, path: filePath, name: path.basename(filePath) };
});

ipcMain.handle('file:openText', async (_e, kind) => {
  const { canceled, filePaths } = await dialog.showOpenDialog(win, {
    title: '불러오기',
    properties: ['openFile'],
    filters: TEXT_FILTERS[kind] || [],
  });
  if (canceled || !filePaths.length) return { ok: false };
  // 인코딩 판별은 렌더러가 하므로 원본 바이트를 그대로 넘긴다
  const buf = await fs.readFile(filePaths[0]);
  return { ok: true, path: filePaths[0], name: path.basename(filePaths[0]), base64: buf.toString('base64') };
});

ipcMain.handle('file:savePng', async (_e, dataUrl, suggestedName) => {
  const { canceled, filePath } = await dialog.showSaveDialog(win, {
    title: 'PNG로 내보내기',
    defaultPath: suggestedName || 'mindmap.png',
    filters: [{ name: 'PNG 이미지', extensions: ['png'] }],
  });
  if (canceled || !filePath) return { ok: false };
  const base64 = dataUrl.replace(/^data:image\/png;base64,/, '');
  await fs.writeFile(filePath, Buffer.from(base64, 'base64'));
  return { ok: true, path: filePath };
});
