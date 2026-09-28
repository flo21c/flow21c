const { contextBridge, ipcRenderer } = require('electron');

// 렌더러(웹 화면)에서 쓸 수 있는 안전한 창구만 열어준다.
contextBridge.exposeInMainWorld('flowmind', {
  isElectron: true,
  saveFile: (json, suggestedName) => ipcRenderer.invoke('file:save', json, suggestedName),
  openFile: () => ipcRenderer.invoke('file:open'),
  savePng: (dataUrl, suggestedName) => ipcRenderer.invoke('file:savePng', dataUrl, suggestedName),
  saveText: (text, suggestedName, kind) => ipcRenderer.invoke('file:saveText', text, suggestedName, kind),
  openText: (kind) => ipcRenderer.invoke('file:openText', kind),
  licenseRead: () => ipcRenderer.invoke('license:read'),
  licenseWrite: (state) => ipcRenderer.invoke('license:write', state),
  machineId: () => ipcRenderer.invoke('machine:id'),
  licenseVerify: (key) => ipcRenderer.invoke('license:verify', key),
});
