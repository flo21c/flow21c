/* =========================================================
   인증키 생성 규칙 (앱과 발급 도구가 함께 쓴다)

   인증키 = HMAC-SHA256(SECRET, 기기코드) 를 32글자 알파벳으로 16자만 뽑은 값.
   기기 코드가 다르면 인증키도 달라지므로, 발급한 PC에서만 인증이 통과한다.

   ※ SECRET 이 유출되면 누구나 아무 PC용 인증키를 만들 수 있습니다.
     이 파일은 고객에게 주는 자료에 절대 넣지 마세요.
   ========================================================= */
'use strict';

const crypto = require('crypto');

// SECRET 은 저장소(공개)에 올리지 않는다. 같은 폴더의 license-secret.js(.gitignore 대상)에서 읽는다.
// 파일 형식: module.exports = '64자리 16진수';  — 만드는 법은 README 참고
const SECRET = require('./license-secret');

// 헷갈리는 I, O, 0, 1을 뺀 32글자. 32는 256의 약수라 난수 편향이 없다.
const ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';

function normalizeCode(v) {
  return String(v || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
}

/** 기기 코드 하나에 대응하는 인증키(16자)를 만든다 */
function keyForMachine(machineId) {
  const mac = crypto.createHmac('sha256', SECRET)
    // 이 문자열은 제품 이름이 바뀌어도 절대 건드리지 말 것.
    // 바꾸는 순간 이미 발급한 인증키가 전부 무효가 된다.
    .update('MindNote-key-v1:' + normalizeCode(machineId))
    .digest();
  let out = '';
  for (let i = 0; i < 16; i++) out += ALPHABET[mac[i] % ALPHABET.length];
  return out;
}

/** 사람이 읽기 좋게 4자씩 끊는다 */
function group(v) {
  return normalizeCode(v).replace(/(.{4})(?=.)/g, '$1-');
}

module.exports = { SECRET, ALPHABET, keyForMachine, normalizeCode, group };
