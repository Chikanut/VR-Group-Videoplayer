import React, { useState, useEffect } from 'react';

/**
 * Minimal QR Code generator - produces a matrix of dark/light modules.
 * Supports only alphanumeric/byte mode, error correction level L, versions 1-4.
 * Sufficient for short URLs like "http://192.168.1.100:8000"
 */
function generateQRMatrix(text) {
  // Use the Canvas API via a hidden element to generate QR,
  // or fall back to a simple text display.
  // Instead, we'll use a pure-JS minimal QR encoder.
  return encodeQR(text);
}

// ── Minimal QR Code encoder (byte mode, EC level L, version auto 1-6) ──────

const EC_CODEWORDS_L = [0, 7, 10, 15, 20, 26, 18]; // version 1-6
const TOTAL_CODEWORDS = [0, 26, 44, 70, 100, 134, 172];
const DATA_CODEWORDS_L = [0, 19, 34, 55, 80, 108, 154];
const BLOCK_INFO_L = [
  null,
  [1, 19],    // v1: 1 block, 19 data codewords
  [1, 34],    // v2
  [1, 55],    // v3
  [1, 80],    // v4
  [1, 108],   // v5
  [2, 77],    // v6: 2 blocks
];

function encodeQR(text) {
  const data = new TextEncoder().encode(text);
  const len = data.length;

  // Pick smallest version that fits
  let version = 0;
  for (let v = 1; v <= 6; v++) {
    const capacity = DATA_CODEWORDS_L[v] - (v >= 10 ? 3 : 2); // mode + length overhead
    if (len <= capacity) { version = v; break; }
  }
  if (!version) version = 6;

  const size = version * 4 + 17;
  const modules = Array.from({ length: size }, () => new Uint8Array(size));
  const isFunction = Array.from({ length: size }, () => new Uint8Array(size));

  // Place finder patterns
  placeFinder(modules, isFunction, 0, 0);
  placeFinder(modules, isFunction, size - 7, 0);
  placeFinder(modules, isFunction, 0, size - 7);

  // Timing patterns
  for (let i = 8; i < size - 8; i++) {
    setFunc(modules, isFunction, 6, i, (i & 1) === 0);
    setFunc(modules, isFunction, i, 6, (i & 1) === 0);
  }

  // Alignment pattern (version >= 2)
  if (version >= 2) {
    const pos = getAlignmentPositions(version);
    for (const r of pos) {
      for (const c of pos) {
        if (isFunction[r][c]) continue;
        placeAlignment(modules, isFunction, r, c);
      }
    }
  }

  // Format info placeholder
  for (let i = 0; i < 8; i++) {
    setFunc(modules, isFunction, 8, i, false);
    setFunc(modules, isFunction, i, 8, false);
  }
  setFunc(modules, isFunction, 8, 8, false);
  for (let i = 0; i < 7; i++) {
    setFunc(modules, isFunction, 8, size - 1 - i, false);
    setFunc(modules, isFunction, size - 1 - i, 8, false);
  }
  setFunc(modules, isFunction, size - 8, 8, true); // dark module

  // Version info (version >= 7 only, we don't need it)

  // Encode data
  const dataBits = encodeDataBits(data, version);
  const ecBits = computeEC(dataBits, version);
  const allBits = [...dataBits, ...ecBits];

  // Place data bits
  placeDataBits(modules, isFunction, allBits, size);

  // Apply mask (mask 0 for simplicity: (row + col) % 2 === 0)
  const mask = 0;
  applyMask(modules, isFunction, mask, size);

  // Place format info
  placeFormatInfo(modules, isFunction, mask, size);

  return modules;
}

function setFunc(modules, isFunction, r, c, val) {
  modules[r][c] = val ? 1 : 0;
  isFunction[r][c] = 1;
}

function placeFinder(modules, isFunction, row, col) {
  for (let r = -1; r <= 7; r++) {
    for (let c = -1; c <= 7; c++) {
      const rr = row + r, cc = col + c;
      if (rr < 0 || rr >= modules.length || cc < 0 || cc >= modules.length) continue;
      const val = (r >= 0 && r <= 6 && (c === 0 || c === 6)) ||
                  (c >= 0 && c <= 6 && (r === 0 || r === 6)) ||
                  (r >= 2 && r <= 4 && c >= 2 && c <= 4);
      setFunc(modules, isFunction, rr, cc, val);
    }
  }
}

function placeAlignment(modules, isFunction, row, col) {
  for (let r = -2; r <= 2; r++) {
    for (let c = -2; c <= 2; c++) {
      const val = Math.max(Math.abs(r), Math.abs(c)) !== 1;
      setFunc(modules, isFunction, row + r, col + c, val);
    }
  }
}

function getAlignmentPositions(version) {
  if (version === 1) return [];
  const last = version * 4 + 10;
  if (version <= 6) return [6, last];
  // For higher versions (not needed here)
  return [6, last];
}

function encodeDataBits(data, version) {
  const bits = [];
  const push = (val, count) => {
    for (let i = count - 1; i >= 0; i--) bits.push((val >>> i) & 1);
  };

  // Mode indicator: byte mode = 0100
  push(4, 4);
  // Character count
  const ccBits = version <= 9 ? 8 : 16;
  push(data.length, ccBits);
  // Data
  for (const b of data) push(b, 8);
  // Terminator
  const totalDataBits = DATA_CODEWORDS_L[version] * 8;
  const termLen = Math.min(4, totalDataBits - bits.length);
  push(0, termLen);
  // Pad to byte boundary
  while (bits.length % 8 !== 0) bits.push(0);
  // Pad codewords
  const padBytes = [0xEC, 0x11];
  let padIdx = 0;
  while (bits.length < totalDataBits) {
    push(padBytes[padIdx % 2], 8);
    padIdx++;
  }
  return bits;
}

function computeEC(dataBits, version) {
  const dataBytes = [];
  for (let i = 0; i < dataBits.length; i += 8) {
    let val = 0;
    for (let j = 0; j < 8; j++) val = (val << 1) | (dataBits[i + j] || 0);
    dataBytes.push(val);
  }

  const ecCount = EC_CODEWORDS_L[version];
  const gen = rsGeneratorPoly(ecCount);
  const ec = rsEncode(dataBytes, gen, ecCount);

  const ecBits = [];
  for (const b of ec) {
    for (let i = 7; i >= 0; i--) ecBits.push((b >>> i) & 1);
  }
  return ecBits;
}

// GF(256) arithmetic for Reed-Solomon
const GF_EXP = new Uint8Array(512);
const GF_LOG = new Uint8Array(256);
(() => {
  let x = 1;
  for (let i = 0; i < 255; i++) {
    GF_EXP[i] = x;
    GF_LOG[x] = i;
    x = (x << 1) ^ (x >= 128 ? 0x11D : 0);
  }
  for (let i = 255; i < 512; i++) GF_EXP[i] = GF_EXP[i - 255];
})();

function gfMul(a, b) {
  if (a === 0 || b === 0) return 0;
  return GF_EXP[GF_LOG[a] + GF_LOG[b]];
}

function rsGeneratorPoly(degree) {
  let gen = [1];
  for (let i = 0; i < degree; i++) {
    const newGen = new Array(gen.length + 1).fill(0);
    for (let j = 0; j < gen.length; j++) {
      newGen[j] ^= gen[j];
      newGen[j + 1] ^= gfMul(gen[j], GF_EXP[i]);
    }
    gen = newGen;
  }
  return gen;
}

function rsEncode(data, gen, ecCount) {
  const msg = new Uint8Array(data.length + ecCount);
  msg.set(data);
  for (let i = 0; i < data.length; i++) {
    const coef = msg[i];
    if (coef === 0) continue;
    for (let j = 0; j < gen.length; j++) {
      msg[i + j] ^= gfMul(gen[j], coef);
    }
  }
  return Array.from(msg.slice(data.length));
}

function placeDataBits(modules, isFunction, bits, size) {
  let bitIdx = 0;
  for (let right = size - 1; right >= 1; right -= 2) {
    if (right === 6) right = 5;
    for (let vert = 0; vert < size; vert++) {
      for (let j = 0; j < 2; j++) {
        const col = right - j;
        const upward = ((right + 1) & 2) === 0;
        const row = upward ? size - 1 - vert : vert;
        if (isFunction[row][col]) continue;
        if (bitIdx < bits.length) {
          modules[row][col] = bits[bitIdx] ? 1 : 0;
          bitIdx++;
        }
      }
    }
  }
}

function applyMask(modules, isFunction, mask, size) {
  for (let r = 0; r < size; r++) {
    for (let c = 0; c < size; c++) {
      if (isFunction[r][c]) continue;
      let invert = false;
      switch (mask) {
        case 0: invert = (r + c) % 2 === 0; break;
        case 1: invert = r % 2 === 0; break;
        case 2: invert = c % 3 === 0; break;
        case 3: invert = (r + c) % 3 === 0; break;
        default: invert = (r + c) % 2 === 0;
      }
      if (invert) modules[r][c] ^= 1;
    }
  }
}

function placeFormatInfo(modules, isFunction, mask, size) {
  // Error correction level L = 01, mask pattern
  const ecl = 1; // L
  const formatData = (ecl << 3) | mask;
  let rem = formatData;
  for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
  const bits = ((formatData << 10) | rem) ^ 0x5412;

  // Place around top-left finder
  for (let i = 0; i < 6; i++) modules[8][i] = (bits >>> i) & 1;
  modules[8][7] = (bits >>> 6) & 1;
  modules[8][8] = (bits >>> 7) & 1;
  modules[7][8] = (bits >>> 8) & 1;
  for (let i = 9; i < 15; i++) modules[14 - i][8] = (bits >>> i) & 1;

  // Place around other finders
  for (let i = 0; i < 8; i++) modules[size - 1 - i][8] = (bits >>> i) & 1;
  for (let i = 8; i < 15; i++) modules[8][size - 15 + i] = (bits >>> i) & 1;
}

// ── QR SVG renderer ─────────────────────────────────────────────────────────

function QRCode({ matrix, size = 200 }) {
  if (!matrix || !matrix.length) return null;
  const n = matrix.length;
  const cellSize = size / (n + 8); // 4-cell quiet zone on each side
  const offset = cellSize * 4;

  const rects = [];
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      if (matrix[r][c]) {
        rects.push(
          <rect
            key={`${r}-${c}`}
            x={offset + c * cellSize}
            y={offset + r * cellSize}
            width={cellSize + 0.5}
            height={cellSize + 0.5}
            fill="#000"
          />
        );
      }
    }
  }

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ background: '#fff', borderRadius: 8 }}>
      {rects}
    </svg>
  );
}

// ── ConnectionButton component ──────────────────────────────────────────────

export default function ConnectionButton() {
  const [open, setOpen] = useState(false);
  const [serverUrl, setServerUrl] = useState('');
  const [qrMatrix, setQrMatrix] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchServerInfo = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/server-info');
      const info = await res.json();
      const url = info.url || `http://${info.ip}:${info.port}`;
      setServerUrl(url);
      setQrMatrix(generateQRMatrix(url));
    } catch (e) {
      // Fallback: use current page URL
      const url = window.location.origin;
      setServerUrl(url);
      setQrMatrix(generateQRMatrix(url));
    }
    setLoading(false);
  };

  const handleOpen = () => {
    setOpen(true);
    fetchServerInfo();
  };

  const handleClose = () => {
    setOpen(false);
  };

  return (
    <>
      <button
        className="connection-btn"
        onClick={handleOpen}
        title="Show QR code for phone connection"
      >
        CONNECTION
      </button>

      {open && (
        <div className="modal-overlay" onClick={handleClose}>
          <div className="modal connection-modal" onClick={e => e.stopPropagation()}>
            <div className="dialog-header">
              <h2 className="dialog-title" style={{ cursor: 'default' }}>Connect from Phone</h2>
              <button className="btn-close" onClick={handleClose}>&times;</button>
            </div>
            <div className="connection-qr-content">
              {loading ? (
                <div className="loading-state" style={{ minHeight: 200 }}>
                  <div className="spinner" />
                  <p>Detecting network...</p>
                </div>
              ) : (
                <>
                  <div className="qr-container">
                    <QRCode matrix={qrMatrix} size={240} />
                  </div>
                  <p className="connection-url">{serverUrl}</p>
                  <p className="connection-hint">
                    Scan QR code with your phone camera or enter the URL in a browser.
                    Make sure both devices are on the same network.
                  </p>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
