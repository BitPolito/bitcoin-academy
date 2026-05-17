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
