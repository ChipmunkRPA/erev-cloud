// QR code encoder (ISO/IEC 18004 byte mode, error-correction level M, versions 1 to 15) for the
// otpauth URI of SF-22:mfa-enrol (SCREENS_B §12.2; 05 SAR-26; BUILD_SPEC WEB-13). The API answers
// `otpauth_uri` and `secret_base32` only, and the frontend carries no QR dependency, so the symbol is
// built here and rendered as a PNG data URI, which the SAR-20 policy `img-src data:` permits. The
// module has no React or DOM dependency; `qr.test.ts` checks the structure of every symbol against the
// standard's layout and its published tables and parses the PNG back to its pixels.
export type QrMatrix = readonly (readonly boolean[])[];

export const MIN_VERSION = 1;
export const MAX_VERSION = 15;
/** ISO/IEC 18004 §6.3.8: four light modules around the symbol. */
export const QUIET_ZONE = 4;

/** Level M error-correction codewords per block, indexed by version (table 9 of the standard). */
const EC_CODEWORDS_PER_BLOCK: readonly number[] = [
  0, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24,
];
/** Level M error-correction blocks, indexed by version. */
const EC_BLOCKS: readonly number[] = [0, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10];
/** Level M indicator of the format information (table 12: L 01, M 00, Q 11, H 10). */
const LEVEL_M_BITS = 0b00;
const FORMAT_GENERATOR = 0x537;
const FORMAT_XOR_MASK = 0x5412;
const VERSION_GENERATOR = 0x1f25;
const GF_POLYNOMIAL = 0x11d;
const PAD_CODEWORDS: readonly number[] = [0xec, 0x11];
const BYTE_MODE = 0b0100;
const MASK_COUNT = 8;
const PENALTY_RUN = 3;
const PENALTY_BLOCK = 3;
const PENALTY_FINDER = 40;
const PENALTY_BALANCE = 10;
const FINDER_LIKE_A: readonly number[] = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0];
const FINDER_LIKE_B: readonly number[] = [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1];

function assertVersion(version: number): void {
  if (!Number.isInteger(version) || version < MIN_VERSION || version > MAX_VERSION) {
    throw new RangeError(
      `QR version ${String(version)} is outside ${MIN_VERSION} to ${MAX_VERSION}`,
    );
  }
}

function tableEntry(table: readonly number[], version: number): number {
  assertVersion(version);
  return table[version] ?? 0;
}

/** Modules available to data and error correction after the function patterns (§7.7.1 table 1). */
export function rawDataModules(version: number): number {
  assertVersion(version);
  let result = (16 * version + 128) * version + 64;
  if (version >= 2) {
    const alignments = Math.floor(version / 7) + 2;
    result -= (25 * alignments - 10) * alignments - 55;
    if (version >= 7) {
      result -= 36;
    }
  }
  return result;
}

export function totalCodewords(version: number): number {
  return Math.floor(rawDataModules(version) / 8);
}

export function dataCodewords(version: number): number {
  return (
    totalCodewords(version) -
    tableEntry(EC_CODEWORDS_PER_BLOCK, version) * tableEntry(EC_BLOCKS, version)
  );
}

/** Bits of the byte-mode character count (table 3). */
export function countBits(version: number): number {
  assertVersion(version);
  return version >= 10 ? 16 : 8;
}

/** Bytes a version carries in byte mode at level M. */
export function byteCapacity(version: number): number {
  return Math.floor((dataCodewords(version) * 8 - 4 - countBits(version)) / 8);
}

/** The smallest version whose byte capacity holds `length` bytes. */
export function versionFor(length: number): number {
  for (let version = MIN_VERSION; version <= MAX_VERSION; version++) {
    if (byteCapacity(version) >= length) {
      return version;
    }
  }
  throw new RangeError(
    `QR content of ${String(length)} bytes exceeds ${String(byteCapacity(MAX_VERSION))} bytes (version ${String(MAX_VERSION)}, level M)`,
  );
}

/** GF(256) product under the QR polynomial x^8 + x^4 + x^3 + x^2 + 1. */
export function gfMultiply(x: number, y: number): number {
  let z = 0;
  for (let i = 7; i >= 0; i--) {
    z = (z << 1) ^ ((z >>> 7) * GF_POLYNOMIAL);
    z ^= ((y >>> i) & 1) * x;
  }
  return z;
}

/** The Reed-Solomon generator polynomial of `degree`, highest power first, without the leading 1. */
export function rsDivisor(degree: number): number[] {
  const result = new Array<number>(degree).fill(0);
  result[degree - 1] = 1;
  let root = 1;
  for (let i = 0; i < degree; i++) {
    for (let j = 0; j < result.length; j++) {
      result[j] = gfMultiply(result[j] ?? 0, root) ^ (result[j + 1] ?? 0);
    }
    root = gfMultiply(root, 2);
  }
  return result;
}

/** The error-correction codewords of `data` under `divisor`. */
export function rsRemainder(data: readonly number[], divisor: readonly number[]): number[] {
  const result = new Array<number>(divisor.length).fill(0);
  for (const byte of data) {
    const factor = byte ^ (result.shift() ?? 0);
    result.push(0);
    divisor.forEach((coefficient, index) => {
      result[index] = (result[index] ?? 0) ^ gfMultiply(coefficient, factor);
    });
  }
  return result;
}

/** Byte-mode data codewords: mode, count, bytes, terminator, byte padding and pad codewords (§7.4). */
export function dataCodewordsOf(bytes: Uint8Array, version: number): number[] {
  const capacity = dataCodewords(version);
  const bits: number[] = [];
  const push = (value: number, length: number) => {
    for (let i = length - 1; i >= 0; i--) {
      bits.push((value >>> i) & 1);
    }
  };
  push(BYTE_MODE, 4);
  push(bytes.length, countBits(version));
  for (const byte of bytes) {
    push(byte, 8);
  }
  if (bits.length > capacity * 8) {
    throw new RangeError(`QR version ${String(version)} cannot hold ${String(bytes.length)} bytes`);
  }
  push(0, Math.min(4, capacity * 8 - bits.length));
  while (bits.length % 8 !== 0) {
    bits.push(0);
  }
  const words: number[] = [];
  for (let i = 0; i < bits.length; i += 8) {
    let word = 0;
    for (let j = 0; j < 8; j++) {
      word = (word << 1) | (bits[i + j] ?? 0);
    }
    words.push(word);
  }
  for (let pad = 0; words.length < capacity; pad++) {
    words.push(PAD_CODEWORDS[pad % PAD_CODEWORDS.length] ?? 0);
  }
  return words;
}

/** Splits the data into blocks, appends error correction and interleaves the codewords (§7.6). */
export function interleave(data: readonly number[], version: number): number[] {
  const blocks = tableEntry(EC_BLOCKS, version);
  const ecLength = tableEntry(EC_CODEWORDS_PER_BLOCK, version);
  const total = totalCodewords(version);
  const shortBlocks = blocks - (total % blocks);
  const shortLength = Math.floor(total / blocks);
  const divisor = rsDivisor(ecLength);
  const rows: number[][] = [];
  let offset = 0;
  for (let i = 0; i < blocks; i++) {
    const length = shortLength - ecLength + (i < shortBlocks ? 0 : 1);
    const block = data.slice(offset, offset + length);
    offset += length;
    const ec = rsRemainder(block, divisor);
    // A short block carries a placeholder where a long block has its extra data codeword, so the
    // column-wise walk below reads every row at the same index.
    rows.push(i < shortBlocks ? [...block, -1, ...ec] : [...block, ...ec]);
  }
  const result: number[] = [];
  for (let i = 0; i <= shortLength; i++) {
    for (const row of rows) {
      const word = row[i];
      if (word !== undefined && word !== -1) {
        result.push(word);
      }
    }
  }
  return result;
}

/** Centre coordinates of the alignment patterns along one axis (annex E). */
export function alignmentPositions(version: number): number[] {
  assertVersion(version);
  if (version === 1) {
    return [];
  }
  const count = Math.floor(version / 7) + 2;
  const size = version * 4 + 17;
  const step = Math.ceil((version * 4 + 4) / (count * 2 - 2)) * 2;
  const result = [6];
  for (let position = size - 7; result.length < count; position -= step) {
    result.splice(1, 0, position);
  }
  return result;
}

/** The 15 format bits of level M and `mask`: BCH(15, 5) remainder, then the fixed XOR mask. */
export function formatInformation(mask: number): number {
  const data = (LEVEL_M_BITS << 3) | mask;
  let remainder = data;
  for (let i = 0; i < 10; i++) {
    remainder = (remainder << 1) ^ ((remainder >>> 9) * FORMAT_GENERATOR);
  }
  return ((data << 10) | remainder) ^ FORMAT_XOR_MASK;
}

/** The 18 version bits (versions 7 and above): BCH(18, 6). */
export function versionInformation(version: number): number {
  assertVersion(version);
  let remainder = version;
  for (let i = 0; i < 12; i++) {
    remainder = (remainder << 1) ^ ((remainder >>> 11) * VERSION_GENERATOR);
  }
  return (version << 12) | remainder;
}

/** The data mask predicate of pattern `mask` at (row, col) (table 10). */
export function maskBit(mask: number, row: number, col: number): boolean {
  switch (mask) {
    case 0:
      return (row + col) % 2 === 0;
    case 1:
      return row % 2 === 0;
    case 2:
      return col % 3 === 0;
    case 3:
      return (row + col) % 3 === 0;
    case 4:
      return (Math.floor(row / 2) + Math.floor(col / 3)) % 2 === 0;
    case 5:
      return ((row * col) % 2) + ((row * col) % 3) === 0;
    case 6:
      return (((row * col) % 2) + ((row * col) % 3)) % 2 === 0;
    case 7:
      return (((row + col) % 2) + ((row * col) % 3)) % 2 === 0;
    default:
      throw new RangeError(`QR mask ${String(mask)} is outside 0 to 7`);
  }
}

interface Canvas {
  readonly size: number;
  /** 1 = dark. */
  readonly modules: Uint8Array;
  /** 1 = a function module (finder, separator, timing, alignment, format, version, dark module). */
  readonly functional: Uint8Array;
}

function isDark(canvas: Canvas, row: number, col: number): boolean {
  return (canvas.modules[row * canvas.size + col] ?? 0) === 1;
}

function setFunction(canvas: Canvas, row: number, col: number, dark: boolean): void {
  const index = row * canvas.size + col;
  canvas.modules[index] = dark ? 1 : 0;
  canvas.functional[index] = 1;
}

function drawFinder(canvas: Canvas, row: number, col: number): void {
  for (let dy = -4; dy <= 4; dy++) {
    for (let dx = -4; dx <= 4; dx++) {
      const r = row + dy;
      const c = col + dx;
      if (r >= 0 && r < canvas.size && c >= 0 && c < canvas.size) {
        const distance = Math.max(Math.abs(dx), Math.abs(dy));
        setFunction(canvas, r, c, distance !== 2 && distance !== 4);
      }
    }
  }
}

function drawAlignment(canvas: Canvas, row: number, col: number): void {
  for (let dy = -2; dy <= 2; dy++) {
    for (let dx = -2; dx <= 2; dx++) {
      setFunction(canvas, row + dy, col + dx, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
    }
  }
}

function drawFormatBits(canvas: Canvas, mask: number): void {
  const bits = formatInformation(mask);
  const bit = (i: number) => ((bits >>> i) & 1) === 1;
  const { size } = canvas;
  for (let i = 0; i <= 5; i++) {
    setFunction(canvas, i, 8, bit(i));
  }
  setFunction(canvas, 7, 8, bit(6));
  setFunction(canvas, 8, 8, bit(7));
  setFunction(canvas, 8, 7, bit(8));
  for (let i = 9; i < 15; i++) {
    setFunction(canvas, 8, 14 - i, bit(i));
  }
  for (let i = 0; i < 8; i++) {
    setFunction(canvas, 8, size - 1 - i, bit(i));
  }
  for (let i = 8; i < 15; i++) {
    setFunction(canvas, size - 15 + i, 8, bit(i));
  }
  setFunction(canvas, size - 8, 8, true);
}

function drawVersion(canvas: Canvas, version: number): void {
  if (version < 7) {
    return;
  }
  const bits = versionInformation(version);
  for (let i = 0; i < 18; i++) {
    const dark = ((bits >>> i) & 1) === 1;
    const a = canvas.size - 11 + (i % 3);
    const b = Math.floor(i / 3);
    setFunction(canvas, b, a, dark);
    setFunction(canvas, a, b, dark);
  }
}

function drawFunctionPatterns(canvas: Canvas, version: number): void {
  const { size } = canvas;
  for (let i = 0; i < size; i++) {
    setFunction(canvas, 6, i, i % 2 === 0);
    setFunction(canvas, i, 6, i % 2 === 0);
  }
  drawFinder(canvas, 3, 3);
  drawFinder(canvas, 3, size - 4);
  drawFinder(canvas, size - 4, 3);
  const positions = alignmentPositions(version);
  const last = positions.length - 1;
  positions.forEach((row, i) => {
    positions.forEach((col, j) => {
      const overlapsFinder =
        (i === 0 && j === 0) || (i === 0 && j === last) || (i === last && j === 0);
      if (!overlapsFinder) {
        drawAlignment(canvas, row, col);
      }
    });
  });
  drawFormatBits(canvas, 0);
  drawVersion(canvas, version);
}

/** Places the codeword bits in the two-column zigzag of §7.7.3; remainder bits stay light. */
function drawCodewords(canvas: Canvas, codewords: readonly number[]): void {
  const { size } = canvas;
  const totalBits = codewords.length * 8;
  let i = 0;
  for (let right = size - 1; right >= 1; right -= 2) {
    if (right === 6) {
      right = 5;
    }
    for (let vertical = 0; vertical < size; vertical++) {
      for (let j = 0; j < 2; j++) {
        const col = right - j;
        const upward = ((right + 1) & 2) === 0;
        const row = upward ? size - 1 - vertical : vertical;
        const index = row * size + col;
        if ((canvas.functional[index] ?? 0) === 0 && i < totalBits) {
          const word = codewords[i >>> 3] ?? 0;
          canvas.modules[index] = (word >>> (7 - (i & 7))) & 1;
          i++;
        }
      }
    }
  }
}

/** XORs the mask over the data modules; applying it twice restores them. */
function applyMask(canvas: Canvas, mask: number): void {
  const { size } = canvas;
  for (let row = 0; row < size; row++) {
    for (let col = 0; col < size; col++) {
      const index = row * size + col;
      if ((canvas.functional[index] ?? 0) === 0 && maskBit(mask, row, col)) {
        canvas.modules[index] = (canvas.modules[index] ?? 0) ^ 1;
      }
    }
  }
}

function linePenalty(at: (k: number) => boolean, size: number): number {
  let score = 0;
  let run = 0;
  let previous: boolean | null = null;
  for (let k = 0; k < size; k++) {
    const value = at(k);
    if (value === previous) {
      run++;
    } else {
      if (run >= 5) {
        score += PENALTY_RUN + run - 5;
      }
      run = 1;
      previous = value;
    }
  }
  if (run >= 5) {
    score += PENALTY_RUN + run - 5;
  }
  for (let start = 0; start + FINDER_LIKE_A.length <= size; start++) {
    let likeA = true;
    let likeB = true;
    for (let k = 0; k < FINDER_LIKE_A.length; k++) {
      const value = at(start + k) ? 1 : 0;
      likeA = likeA && value === FINDER_LIKE_A[k];
      likeB = likeB && value === FINDER_LIKE_B[k];
    }
    score += (likeA ? PENALTY_FINDER : 0) + (likeB ? PENALTY_FINDER : 0);
  }
  return score;
}

/** The §7.8.3 penalty: runs, 2 × 2 blocks, finder-like patterns and the dark proportion. */
function penaltyScore(canvas: Canvas): number {
  const { size } = canvas;
  let score = 0;
  for (let i = 0; i < size; i++) {
    score += linePenalty((k) => isDark(canvas, i, k), size);
    score += linePenalty((k) => isDark(canvas, k, i), size);
  }
  for (let row = 0; row < size - 1; row++) {
    for (let col = 0; col < size - 1; col++) {
      const value = isDark(canvas, row, col);
      if (
        value === isDark(canvas, row, col + 1) &&
        value === isDark(canvas, row + 1, col) &&
        value === isDark(canvas, row + 1, col + 1)
      ) {
        score += PENALTY_BLOCK;
      }
    }
  }
  let dark = 0;
  for (let index = 0; index < size * size; index++) {
    dark += canvas.modules[index] ?? 0;
  }
  const total = size * size;
  const steps = Math.ceil(Math.abs(dark * 20 - total * 10) / total) - 1;
  return score + steps * PENALTY_BALANCE;
}

/** The QR symbol of `text` (UTF-8, byte mode, level M) as rows of dark flags, without a quiet zone. */
export function encodeQr(text: string): QrMatrix {
  const bytes = new TextEncoder().encode(text);
  const version = versionFor(bytes.length);
  const size = version * 4 + 17;
  const canvas: Canvas = {
    size,
    modules: new Uint8Array(size * size),
    functional: new Uint8Array(size * size),
  };
  drawFunctionPatterns(canvas, version);
  drawCodewords(canvas, interleave(dataCodewordsOf(bytes, version), version));
  let best = 0;
  let bestScore = Number.POSITIVE_INFINITY;
  for (let mask = 0; mask < MASK_COUNT; mask++) {
    applyMask(canvas, mask);
    drawFormatBits(canvas, mask);
    const score = penaltyScore(canvas);
    if (score < bestScore) {
      best = mask;
      bestScore = score;
    }
    applyMask(canvas, mask);
  }
  applyMask(canvas, best);
  drawFormatBits(canvas, best);
  const rows: boolean[][] = [];
  for (let row = 0; row < size; row++) {
    const cells: boolean[] = [];
    for (let col = 0; col < size; col++) {
      cells.push(isDark(canvas, row, col));
    }
    rows.push(cells);
  }
  return rows;
}

// --- PNG rendering ----------------------------------------------------------------------------
// The image is a 1-bit greyscale PNG (colour type 0): black modules on a white quiet zone in both
// themes, which SCREENS_B §12.2 fixes as image content. The bytes are written here (a stored-block
// zlib stream, CRC-32 and Adler-32), so the module carries no markup and no colour literal.

/** Pixels per module of the rendered image. */
export const PNG_SCALE = 4;

const PNG_SIGNATURE: readonly number[] = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
const ZLIB_HEADER: readonly number[] = [0x78, 0x01];
const STORED_BLOCK_MAX = 65_535;
const CRC_POLYNOMIAL = 0xedb88320;
const ADLER_MODULUS = 65_521;
const BASE64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

let crcTable: Uint32Array | null = null;

function crc32(bytes: Uint8Array): number {
  if (crcTable === null) {
    crcTable = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) {
        c = (c & 1) === 1 ? CRC_POLYNOMIAL ^ (c >>> 1) : c >>> 1;
      }
      crcTable[n] = c >>> 0;
    }
  }
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc = (crcTable[(crc ^ byte) & 0xff] ?? 0) ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function adler32(bytes: Uint8Array): number {
  let a = 1;
  let b = 0;
  for (const byte of bytes) {
    a = (a + byte) % ADLER_MODULUS;
    b = (b + a) % ADLER_MODULUS;
  }
  return ((b << 16) | a) >>> 0;
}

function uint32BigEndian(value: number): number[] {
  return [(value >>> 24) & 0xff, (value >>> 16) & 0xff, (value >>> 8) & 0xff, value & 0xff];
}

/** A zlib stream of stored (uncompressed) deflate blocks. */
export function zlibStored(data: Uint8Array): Uint8Array {
  const out: number[] = [...ZLIB_HEADER];
  for (let offset = 0; offset < data.length || offset === 0; offset += STORED_BLOCK_MAX) {
    const length = Math.min(STORED_BLOCK_MAX, data.length - offset);
    const final = offset + length >= data.length ? 1 : 0;
    out.push(final, length & 0xff, length >>> 8, ~length & 0xff, (~length >>> 8) & 0xff);
    for (let i = 0; i < length; i++) {
      out.push(data[offset + i] ?? 0);
    }
    if (data.length === 0) {
      break;
    }
  }
  out.push(...uint32BigEndian(adler32(data)));
  return Uint8Array.from(out);
}

function pngChunk(type: string, data: Uint8Array): number[] {
  const typed = Uint8Array.from([...type].map((char) => char.charCodeAt(0)));
  const body = new Uint8Array(typed.length + data.length);
  body.set(typed, 0);
  body.set(data, typed.length);
  return [...uint32BigEndian(data.length), ...body, ...uint32BigEndian(crc32(body))];
}

/** The symbol with its quiet zone as a 1-bit greyscale PNG, `scale` pixels per module. */
export function qrPng(matrix: QrMatrix, scale = PNG_SCALE, quiet = QUIET_ZONE): Uint8Array {
  const extent = matrix.length + 2 * quiet;
  const pixels = extent * scale;
  const rowBytes = Math.ceil(pixels / 8);
  const raster = new Uint8Array(pixels * (1 + rowBytes));
  for (let y = 0; y < pixels; y++) {
    const rowStart = y * (1 + rowBytes);
    raster[rowStart] = 0; // filter type None
    const moduleRow = Math.floor(y / scale) - quiet;
    for (let x = 0; x < pixels; x++) {
      const moduleCol = Math.floor(x / scale) - quiet;
      const dark = matrix[moduleRow]?.[moduleCol] === true;
      if (!dark) {
        const index = rowStart + 1 + (x >>> 3);
        raster[index] = (raster[index] ?? 0) | (0x80 >>> (x & 7));
      }
    }
  }
  const header = Uint8Array.from([
    ...uint32BigEndian(pixels),
    ...uint32BigEndian(pixels),
    1, // bit depth
    0, // colour type: greyscale
    0, // compression
    0, // filter
    0, // interlace
  ]);
  return Uint8Array.from([
    ...PNG_SIGNATURE,
    ...pngChunk("IHDR", header),
    ...pngChunk("IDAT", zlibStored(raster)),
    ...pngChunk("IEND", new Uint8Array(0)),
  ]);
}

export function toBase64(bytes: Uint8Array): string {
  let out = "";
  for (let i = 0; i < bytes.length; i += 3) {
    const a = bytes[i] ?? 0;
    const b = bytes[i + 1];
    const c = bytes[i + 2];
    const triple = (a << 16) | ((b ?? 0) << 8) | (c ?? 0);
    out += BASE64_ALPHABET[(triple >>> 18) & 63] ?? "";
    out += BASE64_ALPHABET[(triple >>> 12) & 63] ?? "";
    out += b === undefined ? "=" : (BASE64_ALPHABET[(triple >>> 6) & 63] ?? "");
    out += c === undefined ? "=" : (BASE64_ALPHABET[triple & 63] ?? "");
  }
  return out;
}

/** The symbol as a PNG data URI for an `img` (SAR-20 `img-src data:`). */
export function qrPngDataUri(matrix: QrMatrix, scale = PNG_SCALE, quiet = QUIET_ZONE): string {
  return `data:image/png;base64,${toBase64(qrPng(matrix, scale, quiet))}`;
}
