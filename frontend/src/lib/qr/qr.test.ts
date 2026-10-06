// QR encoder tests (BUILD_SPEC WEB-13; SCREENS_B §12.2; supervisor ruling D-98 candidate 24, Q2):
// structural checks of every produced symbol (dimension per version, finder patterns and separators,
// timing patterns, the dark module, alignment centres, both format-information copies against the
// published level-M table, the version information against the published table, the count of data
// modules) plus the published reference vectors of ISO/IEC 18004: the format-information table for
// level M (annex C), the version-information table for versions 7 to 15 (annex D), the alignment-centre
// table (annex E), the byte-mode capacities and codeword totals (tables 7 and 9), and two published
// Reed-Solomon examples (annex I, `01234567` 1-M; the 1-M `HELLO WORLD` example). No published
// full-symbol textual vector exists for a version 5 or larger byte-mode input, so the version-6 otpauth
// symbol is covered by the structural checks; a scan by a real authenticator is the persona QA
// prerequisite (lane record F-ADM, slice E).
import { describe, expect, it } from "vitest";

import {
  alignmentPositions,
  byteCapacity,
  dataCodewordsOf,
  encodeQr,
  formatInformation,
  interleave,
  MAX_VERSION,
  PNG_SCALE,
  type QrMatrix,
  qrPngDataUri,
  rawDataModules,
  rsDivisor,
  rsRemainder,
  toBase64,
  totalCodewords,
  versionFor,
  versionInformation,
  zlibStored,
} from "./qr";

/** Level M format information by mask (annex C, table C.1). */
const FORMAT_M = [0x5412, 0x5125, 0x5e7c, 0x5b4b, 0x45f9, 0x40ce, 0x4f97, 0x4aa0];
/** Version information for versions 7 to 15 (annex D, table D.1). */
const VERSION_INFO: Readonly<Record<number, number>> = {
  7: 0x07c94,
  8: 0x085bc,
  9: 0x09a99,
  10: 0x0a4d3,
  11: 0x0bbf6,
  12: 0x0c762,
  13: 0x0d847,
  14: 0x0e60d,
  15: 0x0f928,
};
/** Total codewords by version (table 9). */
const TOTAL = [0, 26, 44, 70, 100, 134, 172, 196, 242, 292, 346, 404, 466, 532, 581, 655];
/** Byte-mode capacity at level M by version (table 7). */
const CAPACITY = [0, 14, 26, 42, 62, 84, 106, 122, 152, 180, 213, 251, 287, 331, 362, 412];
/** Alignment pattern centres by version (annex E, table E.1). */
const ALIGNMENT: Readonly<Record<number, readonly number[]>> = {
  1: [],
  2: [6, 18],
  3: [6, 22],
  4: [6, 26],
  5: [6, 30],
  6: [6, 34],
  7: [6, 22, 38],
  8: [6, 24, 42],
  9: [6, 26, 46],
  10: [6, 28, 50],
  11: [6, 30, 54],
  12: [6, 32, 58],
  13: [6, 34, 62],
  14: [6, 26, 46, 66],
  15: [6, 26, 48, 70],
};
/** Remainder bits after the codewords, by version (table 1). */
const REMAINDER = [0, 0, 7, 7, 7, 7, 7, 0, 0, 0, 0, 0, 0, 0, 3, 3];

const OTPAUTH =
  "otpauth://totp/eRev:maya%40example.test?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&issuer=eRev";

interface Png {
  readonly width: number;
  readonly height: number;
  readonly bitDepth: number;
  readonly colourType: number;
  /** The filtered scanlines after inflating the stored blocks. */
  readonly raster: Uint8Array;
}

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let k = 0; k < 8; k++) {
      crc = (crc & 1) === 1 ? 0xedb88320 ^ (crc >>> 1) : crc >>> 1;
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function readUint32(bytes: Uint8Array, offset: number): number {
  return (
    (((bytes[offset] ?? 0) << 24) |
      ((bytes[offset + 1] ?? 0) << 16) |
      ((bytes[offset + 2] ?? 0) << 8) |
      (bytes[offset + 3] ?? 0)) >>>
    0
  );
}

/** Parses the PNG the encoder writes: signature, chunk CRCs, IHDR and a stored-block zlib IDAT. */
function parsePng(bytes: Uint8Array): Png {
  expect([...bytes.slice(0, 8)]).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  const chunks: Array<{ type: string; data: Uint8Array }> = [];
  let offset = 8;
  while (offset < bytes.length) {
    const length = readUint32(bytes, offset);
    const type = String.fromCharCode(...bytes.slice(offset + 4, offset + 8));
    const data = bytes.slice(offset + 8, offset + 8 + length);
    expect(readUint32(bytes, offset + 8 + length)).toBe(
      crc32(bytes.slice(offset + 4, offset + 8 + length)),
    );
    chunks.push({ type, data });
    offset += 12 + length;
  }
  expect(chunks.map((chunk) => chunk.type)).toEqual(["IHDR", "IDAT", "IEND"]);
  const header = chunks[0]?.data ?? new Uint8Array(0);
  const idat = chunks[1]?.data ?? new Uint8Array(0);
  expect([...idat.slice(0, 2)]).toEqual([0x78, 0x01]);
  const raster: number[] = [];
  let cursor = 2;
  for (;;) {
    const flags = idat[cursor] ?? 0;
    expect((flags >>> 1) & 3).toBe(0);
    const length = (idat[cursor + 1] ?? 0) | ((idat[cursor + 2] ?? 0) << 8);
    const complement = (idat[cursor + 3] ?? 0) | ((idat[cursor + 4] ?? 0) << 8);
    expect(complement).toBe(~length & 0xffff);
    raster.push(...idat.slice(cursor + 5, cursor + 5 + length));
    cursor += 5 + length;
    if ((flags & 1) === 1) {
      break;
    }
  }
  let a = 1;
  let b = 0;
  for (const byte of raster) {
    a = (a + byte) % 65_521;
    b = (b + a) % 65_521;
  }
  expect(readUint32(idat, cursor)).toBe(((b << 16) | a) >>> 0);
  expect(cursor + 4).toBe(idat.length);
  return {
    width: readUint32(header, 0),
    height: readUint32(header, 4),
    bitDepth: header[8] ?? -1,
    colourType: header[9] ?? -1,
    raster: Uint8Array.from(raster),
  };
}

/** The function-module positions of a version, built here from the standard's layout rules. */
function functionModules(version: number): Set<number> {
  const size = version * 4 + 17;
  const key = (row: number, col: number) => row * size + col;
  const set = new Set<number>();
  for (const [row, col] of [
    [3, 3],
    [3, size - 4],
    [size - 4, 3],
  ] as const) {
    for (let dy = -4; dy <= 4; dy++) {
      for (let dx = -4; dx <= 4; dx++) {
        const r = row + dy;
        const c = col + dx;
        if (r >= 0 && c >= 0 && r < size && c < size) {
          set.add(key(r, c));
        }
      }
    }
  }
  for (let k = 0; k < size; k++) {
    set.add(key(6, k));
    set.add(key(k, 6));
  }
  set.add(key(size - 8, 8));
  const centres = ALIGNMENT[version] ?? [];
  const last = centres.length - 1;
  centres.forEach((row, i) => {
    centres.forEach((col, j) => {
      if ((i === 0 && j === 0) || (i === 0 && j === last) || (i === last && j === 0)) {
        return;
      }
      for (let dy = -2; dy <= 2; dy++) {
        for (let dx = -2; dx <= 2; dx++) {
          set.add(key(row + dy, col + dx));
        }
      }
    });
  });
  for (let i = 0; i <= 8; i++) {
    set.add(key(i, 8));
    set.add(key(8, i));
  }
  for (let i = 0; i < 8; i++) {
    set.add(key(8, size - 1 - i));
    set.add(key(size - 1 - i, 8));
  }
  if (version >= 7) {
    for (let i = 0; i < 18; i++) {
      const a = size - 11 + (i % 3);
      const b = Math.floor(i / 3);
      set.add(key(a, b));
      set.add(key(b, a));
    }
  }
  return set;
}

/** The structural checks of one symbol; returns the mask its format information names. */
function checkStructure(matrix: QrMatrix, version: number): number {
  const size = version * 4 + 17;
  expect(matrix.length).toBe(size);
  for (const row of matrix) {
    expect(row.length).toBe(size);
  }
  const dark = (row: number, col: number): boolean => matrix[row]?.[col] === true;

  // Finder patterns with their light separators.
  for (const [row, col] of [
    [3, 3],
    [3, size - 4],
    [size - 4, 3],
  ] as const) {
    for (let dy = -4; dy <= 4; dy++) {
      for (let dx = -4; dx <= 4; dx++) {
        const r = row + dy;
        const c = col + dx;
        if (r < 0 || c < 0 || r >= size || c >= size) {
          continue;
        }
        const distance = Math.max(Math.abs(dx), Math.abs(dy));
        expect(dark(r, c)).toBe(distance !== 2 && distance !== 4);
      }
    }
  }
  // Timing patterns between the finders.
  for (let k = 8; k <= size - 9; k++) {
    expect(dark(6, k)).toBe(k % 2 === 0);
    expect(dark(k, 6)).toBe(k % 2 === 0);
  }
  // The dark module.
  expect(dark(size - 8, 8)).toBe(true);
  // Alignment patterns.
  const centres = ALIGNMENT[version] ?? [];
  const last = centres.length - 1;
  centres.forEach((row, i) => {
    centres.forEach((col, j) => {
      if ((i === 0 && j === 0) || (i === 0 && j === last) || (i === last && j === 0)) {
        return;
      }
      for (let dy = -2; dy <= 2; dy++) {
        for (let dx = -2; dx <= 2; dx++) {
          expect(dark(row + dy, col + dx)).toBe(Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
        }
      }
    });
  });
  // Format information, both copies, level M.
  const first: boolean[] = [];
  for (let i = 0; i <= 5; i++) {
    first.push(dark(i, 8));
  }
  first.push(dark(7, 8), dark(8, 8), dark(8, 7));
  for (let i = 9; i < 15; i++) {
    first.push(dark(8, 14 - i));
  }
  const second: boolean[] = [];
  for (let i = 0; i < 8; i++) {
    second.push(dark(8, size - 1 - i));
  }
  for (let i = 8; i < 15; i++) {
    second.push(dark(size - 15 + i, 8));
  }
  expect(second).toEqual(first);
  const format = first.reduce((value, bit, i) => value | ((bit ? 1 : 0) << i), 0);
  const mask = FORMAT_M.indexOf(format);
  expect(mask).toBeGreaterThanOrEqual(0);
  // Version information, both copies, against the published table.
  if (version >= 7) {
    let bits = 0;
    for (let i = 0; i < 18; i++) {
      const a = size - 11 + (i % 3);
      const b = Math.floor(i / 3);
      expect(dark(a, b)).toBe(dark(b, a));
      bits |= (dark(b, a) ? 1 : 0) << i;
    }
    expect(bits).toBe(VERSION_INFO[version]);
  }
  // Every other module is a data module.
  const functional = functionModules(version);
  expect(size * size - functional.size).toBe(rawDataModules(version));
  return mask;
}

describe("published tables", () => {
  it("codeword totals, byte capacities, remainder bits and alignment centres follow the standard", () => {
    for (let version = 1; version <= MAX_VERSION; version++) {
      expect(totalCodewords(version)).toBe(TOTAL[version]);
      expect(byteCapacity(version)).toBe(CAPACITY[version]);
      expect(rawDataModules(version) - 8 * totalCodewords(version)).toBe(REMAINDER[version]);
      expect(alignmentPositions(version)).toEqual(ALIGNMENT[version]);
    }
    expect(versionFor(0)).toBe(1);
    expect(versionFor(14)).toBe(1);
    expect(versionFor(15)).toBe(2);
    expect(versionFor(106)).toBe(6);
    expect(versionFor(107)).toBe(7);
    expect(versionFor(412)).toBe(15);
    expect(() => versionFor(413)).toThrow(RangeError);
  });

  it("format information matches the level-M table for every mask", () => {
    for (let mask = 0; mask < 8; mask++) {
      expect(formatInformation(mask)).toBe(FORMAT_M[mask]);
    }
  });

  it("version information matches the published table for versions 7 to 15", () => {
    for (let version = 7; version <= MAX_VERSION; version++) {
      expect(versionInformation(version)).toBe(VERSION_INFO[version]);
    }
  });

  it("Reed-Solomon codewords match the two published 1-M examples", () => {
    // ISO/IEC 18004 annex I: numeric "01234567", version 1-M.
    const annexI = [
      0x10, 0x20, 0x0c, 0x56, 0x61, 0x80, 0xec, 0x11, 0xec, 0x11, 0xec, 0x11, 0xec, 0x11, 0xec,
      0x11,
    ];
    expect(rsRemainder(annexI, rsDivisor(10))).toEqual([
      0xa5, 0x24, 0xd4, 0xc1, 0xed, 0x36, 0xc7, 0x87, 0x2c, 0x55,
    ]);
    // The widely published alphanumeric "HELLO WORLD" 1-M example.
    const helloWorld = [
      0x20, 0x5b, 0x0b, 0x78, 0xd1, 0x72, 0xdc, 0x4d, 0x43, 0x40, 0xec, 0x11, 0xec, 0x11, 0xec,
      0x11,
    ];
    expect(rsRemainder(helloWorld, rsDivisor(10))).toEqual([
      196, 35, 39, 119, 235, 215, 231, 226, 93, 23,
    ]);
  });

  it("byte-mode data codewords follow the §7.4 procedure for HELLO WORLD at version 1", () => {
    // Derived by hand from the procedure: mode 0100, count 00001011, eleven bytes, terminator 0000,
    // then the pad codewords EC 11 EC to the 16 data codewords of 1-M.
    const bytes = new TextEncoder().encode("HELLO WORLD");
    expect(dataCodewordsOf(bytes, 1)).toEqual([
      0x40, 0xb4, 0x84, 0x54, 0xc4, 0xc4, 0xf2, 0x05, 0x74, 0xf5, 0x24, 0xc4, 0x40, 0xec, 0x11,
      0xec,
    ]);
    // One block at version 1: the data codewords are followed by their ten EC codewords.
    const codewords = interleave(dataCodewordsOf(bytes, 1), 1);
    expect(codewords).toHaveLength(26);
    expect(codewords.slice(0, 16)).toEqual(dataCodewordsOf(bytes, 1));
    expect(codewords.slice(16)).toEqual(rsRemainder(dataCodewordsOf(bytes, 1), rsDivisor(10)));
  });
});

describe("encodeQr", () => {
  it.each([
    ["", 1],
    ["HELLO WORLD", 1],
    ["x".repeat(26), 2],
    ["The quick brown fox jumps over the lazy dog", 4],
    [OTPAUTH, 6],
    ["é".repeat(60), 7],
    ["x".repeat(213), 10],
    ["y".repeat(412), 15],
  ])("builds a structurally valid version-%i symbol for %j", (text, version) => {
    const matrix = encodeQr(text);
    const mask = checkStructure(matrix, version);
    expect(mask).toBeGreaterThanOrEqual(0);
    expect(mask).toBeLessThan(8);
  });

  it("chooses the version from the UTF-8 length and refuses content beyond version 15", () => {
    expect(encodeQr("é".repeat(53)).length).toBe(6 * 4 + 17);
    expect(encodeQr("é".repeat(54)).length).toBe(7 * 4 + 17);
    expect(() => encodeQr("z".repeat(413))).toThrow(RangeError);
  });

  it("renders a 1-bit greyscale PNG data URI with the quiet zone; every pixel follows its module", () => {
    const matrix = encodeQr(OTPAUTH);
    const uri = qrPngDataUri(matrix);
    expect(uri.startsWith("data:image/png;base64,")).toBe(true);
    const bytes = Uint8Array.from(atob(uri.slice("data:image/png;base64,".length)), (char) =>
      char.charCodeAt(0),
    );
    const extent = matrix.length + 8;
    const pixels = extent * PNG_SCALE;
    const image = parsePng(bytes);
    expect(image.width).toBe(pixels);
    expect(image.height).toBe(pixels);
    expect([image.bitDepth, image.colourType]).toEqual([1, 0]);
    const rowBytes = Math.ceil(pixels / 8);
    expect(image.raster.length).toBe(pixels * (1 + rowBytes));
    const white = (x: number, y: number): boolean => {
      const index = y * (1 + rowBytes) + 1 + (x >>> 3);
      expect(image.raster[y * (1 + rowBytes)]).toBe(0);
      return (((image.raster[index] ?? 0) >>> (7 - (x & 7))) & 1) === 1;
    };
    for (let y = 0; y < pixels; y++) {
      for (let x = 0; x < pixels; x++) {
        const row = Math.floor(y / PNG_SCALE) - 4;
        const col = Math.floor(x / PNG_SCALE) - 4;
        const dark = matrix[row]?.[col] === true;
        expect(white(x, y)).toBe(!dark);
      }
    }
  });

  it("base64 and the stored zlib stream follow their formats", () => {
    expect(toBase64(new Uint8Array([]))).toBe("");
    expect(toBase64(Uint8Array.from([0x4d]))).toBe("TQ==");
    expect(toBase64(Uint8Array.from([0x4d, 0x61]))).toBe("TWE=");
    expect(toBase64(Uint8Array.from([0x4d, 0x61, 0x6e]))).toBe("TWFu");
    const data = Uint8Array.from([1, 2, 3, 4, 5]);
    const stream = zlibStored(data);
    expect([...stream.slice(0, 2)]).toEqual([0x78, 0x01]);
    // BFINAL 1, BTYPE 00; LEN 5 little-endian; NLEN = ~LEN.
    expect([...stream.slice(2, 7)]).toEqual([1, 5, 0, 0xfa, 0xff]);
    expect([...stream.slice(7, 12)]).toEqual([1, 2, 3, 4, 5]);
    // Adler-32 of 1..5: a = 16, b = 1+3+6+10+15 + 5 = 40 → 0x00280010.
    expect([...stream.slice(12)]).toEqual([0x00, 0x28, 0x00, 0x10]);
  });
});
