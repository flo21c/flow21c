/* =========================================================
   인증키 발급 도구 (판매자 전용, 고객에게 주지 말 것)

   사용법:  node tools/keygen.js <기기코드> [<기기코드> ...]
   고객이 앱의 인증 화면에서 알려준 기기 코드를 넣으면 그 PC 전용 인증키가 나온다.
   ========================================================= */
'use strict';

const { keyForMachine, normalizeCode, group } = require('../license-core');

const codes = process.argv.slice(2);
if (!codes.length) {
  console.error('사용법: node tools/keygen.js <기기코드> [<기기코드> ...]');
  process.exit(1);
}

for (const c of codes) {
  const mid = normalizeCode(c);
  if (mid.length !== 16) {
    console.error(`기기 코드는 16자여야 합니다: ${c} (${mid.length}자)`);
    process.exitCode = 1;
    continue;
  }
  console.log(`${group(mid)}  →  ${group(keyForMachine(mid))}`);
}
