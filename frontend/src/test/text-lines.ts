// The lines a sentence takes in a box, measured in the product's own Inter file (DESIGN_SYSTEM DS-TYP-01,
// DS-TYP-05). A test of rendered text cannot see what CSS cuts: jsdom lays nothing out, and `getByText`
// passes on a line the browser clamps. A component that limits its lines — a toast holds two (DS-CMP-22)
// — is therefore held to them here, by measure: the advance widths of the font's `hmtx` table at the
// default instance of the variable font (weight 400, optical size 14, which `font-optical-sizing: auto`
// selects for `body-sm`), summed per character and broken greedily at spaces, as a browser breaks plain
// text. Kerning (GPOS) is not applied, so a line is never measured shorter than the browser draws it by
// more than a pixel or two; a sentence that needs a third line by this measure needs it in the browser.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { brotliDecompressSync } from "node:zlib";

// The module's own address as a string: under jsdom the global `URL` is not the one Node reads.
const INTER = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../assets/fonts/inter/inter-latin-opsz-normal.woff2",
);

/** The table tags a WOFF2 directory names by index (WOFF2 §5.2). */
const KNOWN_TAGS: readonly string[] = [
  ..."cmap head hhea hmtx maxp name OS/2 post".split(" "),
  "cvt ",
  ..."fpgm glyf loca prep".split(" "),
  "CFF ",
  ..."VORG EBDT EBLC gasp hdmx kern LTSH PCLT VDMX vhea vmtx BASE GDEF GPOS GSUB EBSC JSTF MATH".split(
    " ",
  ),
  ..."CBDT CBLC COLR CPAL".split(" "),
  "SVG ",
  ..."sbix acnt avar bdat bloc bsln cvar fdsc feat fmtx fvar gvar hsty just lcar mort morx opbd".split(
    " ",
  ),
  ..."prop trak Zapf Silf Glat Gloc Feat Sill".split(" "),
];

interface Table {
  readonly transformed: boolean;
  readonly bytes: Uint8Array;
}

function view(bytes: Uint8Array): DataView {
  return new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
}

/** The tables of a WOFF2 file: its directory, then one Brotli stream that holds them in that order. */
function tablesOf(file: Uint8Array): ReadonlyMap<string, Table> {
  const header = view(file);
  if (header.getUint32(0) !== 0x774f4632) {
    throw new Error("not a WOFF2 file");
  }
  const count = header.getUint16(12);
  const compressedSize = header.getUint32(20);
  let at = 48;
  const base128 = (): number => {
    let value = 0;
    for (let index = 0; index < 5; index += 1) {
      const byte = header.getUint8(at);
      at += 1;
      value = value * 128 + (byte & 0x7f);
      if ((byte & 0x80) === 0) {
        return value;
      }
    }
    throw new Error("a table length of the WOFF2 directory does not end");
  };
  const entries: {
    readonly tag: string;
    readonly transformed: boolean;
    readonly length: number;
  }[] = [];
  for (let index = 0; index < count; index += 1) {
    const flags = header.getUint8(at);
    at += 1;
    let tag = KNOWN_TAGS[flags & 0x3f];
    if (tag === undefined) {
      tag = String.fromCharCode(...file.subarray(at, at + 4));
      at += 4;
    }
    const version = flags >> 6;
    const origLength = base128();
    // `glyf` and `loca` are transformed at version 0, every other table at a version other than 0.
    const transformed = tag === "glyf" || tag === "loca" ? version === 0 : version !== 0;
    entries.push({ tag, transformed, length: transformed ? base128() : origLength });
  }
  const data = brotliDecompressSync(file.subarray(at, at + compressedSize));
  const tables = new Map<string, Table>();
  let offset = 0;
  for (const entry of entries) {
    tables.set(entry.tag, {
      transformed: entry.transformed,
      bytes: data.subarray(offset, offset + entry.length),
    });
    offset += entry.length;
  }
  return tables;
}

function table(tables: ReadonlyMap<string, Table>, tag: string): Table {
  const found = tables.get(tag);
  if (found === undefined) {
    throw new Error(`the font has no ${tag} table`);
  }
  return found;
}

/** Code point to glyph, from the Unicode subtable of `cmap` (format 12, else format 4). */
function glyphsOf(cmap: Uint8Array): ReadonlyMap<number, number> {
  const data = view(cmap);
  let best: { readonly offset: number; readonly format: number } | null = null;
  for (let index = 0; index < data.getUint16(2); index += 1) {
    const platform = data.getUint16(4 + index * 8);
    const offset = data.getUint32(8 + index * 8);
    const format = data.getUint16(offset);
    const unicode = platform === 0 || platform === 3;
    if (unicode && (format === 12 || (format === 4 && best?.format !== 12))) {
      best = { offset, format };
    }
  }
  if (best === null) {
    throw new Error("the font has no Unicode cmap of format 4 or 12");
  }
  const glyphs = new Map<number, number>();
  const { offset } = best;
  if (best.format === 12) {
    for (let index = 0; index < data.getUint32(offset + 12); index += 1) {
      const start = data.getUint32(offset + 16 + index * 12);
      const end = data.getUint32(offset + 20 + index * 12);
      const first = data.getUint32(offset + 24 + index * 12);
      for (let code = start; code <= end; code += 1) {
        glyphs.set(code, first + (code - start));
      }
    }
    return glyphs;
  }
  const segments = data.getUint16(offset + 6) / 2;
  const ends = offset + 14;
  const starts = ends + segments * 2 + 2;
  const deltas = starts + segments * 2;
  const ranges = deltas + segments * 2;
  for (let index = 0; index < segments; index += 1) {
    const end = data.getUint16(ends + index * 2);
    const start = data.getUint16(starts + index * 2);
    const delta = data.getInt16(deltas + index * 2);
    const range = data.getUint16(ranges + index * 2);
    for (let code = start; code <= end && code !== 0xffff; code += 1) {
      let glyph = (code + delta) & 0xffff;
      if (range !== 0) {
        glyph = data.getUint16(ranges + index * 2 + range + (code - start) * 2);
        glyph = glyph === 0 ? 0 : (glyph + delta) & 0xffff;
      }
      glyphs.set(code, glyph);
    }
  }
  return glyphs;
}

interface Font {
  readonly unitsPerEm: number;
  readonly glyphs: ReadonlyMap<number, number>;
  /** The advance width of a glyph, in font units. */
  readonly advance: (glyph: number) => number;
}

function readFont(): Font {
  const tables = tablesOf(readFileSync(INTER));
  const metrics = view(table(tables, "hhea").bytes).getUint16(34);
  const hmtx = table(tables, "hmtx");
  const widths = view(hmtx.bytes);
  return {
    unitsPerEm: view(table(tables, "head").bytes).getUint16(18),
    glyphs: glyphsOf(table(tables, "cmap").bytes),
    // The glyphs after the last metric share its advance. A transformed table (WOFF2 §5.4) is a flags
    // byte and then the advance widths alone.
    advance: (glyph) => {
      const slot = Math.min(glyph, metrics - 1);
      return hmtx.transformed ? widths.getUint16(1 + slot * 2) : widths.getUint16(slot * 4);
    },
  };
}

let font: Font | null = null;

/** The width of `text` on one line, in CSS pixels at `fontSize`. */
export function textWidth(text: string, fontSize: number): number {
  font ??= readFont();
  let units = 0;
  for (const character of text) {
    const glyph = font.glyphs.get(character.codePointAt(0) ?? 0);
    if (glyph === undefined) {
      throw new Error(`the latin Inter file has no glyph for ${JSON.stringify(character)}`);
    }
    units += font.advance(glyph);
  }
  return (units / font.unitsPerEm) * fontSize;
}

export interface TextBox {
  /** CSS pixels. */
  readonly fontSize: number;
  /** The width the text may take, in CSS pixels. */
  readonly width: number;
}

/** The lines a box breaks `text` into: at spaces, each line as long as it fits. */
export function textLines(text: string, box: TextBox): readonly string[] {
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(" ")) {
    const longer = line === "" ? word : `${line} ${word}`;
    if (line !== "" && textWidth(longer, box.fontSize) > box.width) {
      lines.push(line);
      line = word;
    } else {
      line = longer;
    }
  }
  lines.push(line);
  return lines;
}

/**
 * The message box of a toast (DESIGN_SYSTEM DS-CMP-22; components/feedback/Toast.tsx): the toast is
 * 360 px wide with a 1 px border and 12 px padding; beside the message stand the 16 px tone icon and
 * the close button — 28 px at the comfortable density — each 12 px away. 360 − 2 − 24 − 16 − 12 − 12 −
 * 28 = 266 px of `body-sm` (13 px). The kit clamps the message at two lines.
 */
export const TOAST_MESSAGE_BOX: TextBox = { fontSize: 13, width: 266 };
export const TOAST_LINES = 2;
