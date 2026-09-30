// Learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';

// jsdom doesn't implement crypto.randomUUID — polyfill via Node.js built-in
if (typeof globalThis.crypto !== 'undefined' && !globalThis.crypto.randomUUID) {
  const nodeCrypto = require('node:crypto');
  Object.defineProperty(globalThis.crypto, 'randomUUID', {
    value: nodeCrypto.randomUUID.bind(nodeCrypto),
    writable: true,
    configurable: true,
  });
}

// jsdom provides neither TextEncoder nor TextDecoder. The SSE client in
// lib/services/study.ts decodes streamed chunks with TextDecoder, so without
// these any test touching the streaming path fails on a ReferenceError rather
// than on anything to do with the code under test.
const { TextEncoder, TextDecoder } = require('node:util');
if (typeof globalThis.TextEncoder === 'undefined') {
  globalThis.TextEncoder = TextEncoder;
}
if (typeof globalThis.TextDecoder === 'undefined') {
  globalThis.TextDecoder = TextDecoder;
}
