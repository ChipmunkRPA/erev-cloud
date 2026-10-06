// Colour arithmetic for the token verification suites DS-VER-01 and DS-VER-02
// (docs/design/DESIGN_SYSTEM.md §2.1 DS-COL-02, §5.2 DS-VIZ-02).
// OKLCH → linear sRGB with the Ottosson matrices, sRGB gamma encoding rounded to 8 bits per
// channel, WCAG 2.x relative luminance and contrast, and the Machado, Oliveira and Fernandes (2009)
// colour-vision deficiency simulation at severity 1.0 on linear RGB, with ΔE = 100 × OKLab distance.

import { readFileSync } from "node:fs";

export type Rgb8 = readonly [number, number, number];
export type Lab = readonly [number, number, number];
export type Tokens = ReadonlyMap<string, string>;
export type Theme = "light" | "dark";

const OKLCH = /^oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\)$/;
const ALIAS = /^var\((--[\w-]+)\)$/;

export function oklchToLinear(l: number, c: number, hueDegrees: number): Lab {
  const h = (hueDegrees * Math.PI) / 180;
  const a = c * Math.cos(h);
  const b = c * Math.sin(h);
  const lp = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const mp = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const sp = (l - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    4.0767416621 * lp - 3.3077115913 * mp + 0.2309699292 * sp,
    -1.2684380046 * lp + 2.6097574011 * mp - 0.3413193965 * sp,
    -0.0041960863 * lp - 0.7034186147 * mp + 1.707614701 * sp,
  ];
}

function encode(linear: number): number {
  const v = Math.min(1, Math.max(0, linear));
  const gamma = v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055;
  return Math.round(gamma * 255);
}

function decode(channel: number): number {
  const v = channel / 255;
  return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
}

/** The 8-bit sRGB rendering of an `oklch(L C H)` value (DS-COL-02). */
export function oklchToRgb8(value: string): Rgb8 {
  const match = OKLCH.exec(value.trim());
  if (match === null) {
    throw new Error(`not an opaque oklch() value: ${value}`);
  }
  const [r, g, b] = oklchToLinear(Number(match[1]), Number(match[2]), Number(match[3]));
  return [encode(r), encode(g), encode(b)];
}

export function linearRgb(rgb: Rgb8): Lab {
  return [decode(rgb[0]), decode(rgb[1]), decode(rgb[2])];
}

export function luminance(rgb: Rgb8): number {
  const [r, g, b] = linearRgb(rgb);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(a: Rgb8, b: Rgb8): number {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (high + 0.05) / (low + 0.05);
}

export function linearToOklab([r, g, b]: Lab): Lab {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

export type Vision = "normal" | "protanopia" | "deuteranopia" | "tritanopia";

const MACHADO: Record<Exclude<Vision, "normal">, readonly Lab[]> = {
  protanopia: [
    [0.152286, 1.052583, -0.204868],
    [0.114503, 0.786281, 0.099216],
    [-0.003882, -0.048116, 1.051998],
  ],
  deuteranopia: [
    [0.367322, 0.860646, -0.227968],
    [0.280085, 0.672501, 0.047413],
    [-0.01182, 0.04294, 0.968881],
  ],
  tritanopia: [
    [1.255528, -0.076749, -0.178779],
    [-0.078411, 0.930809, 0.147602],
    [0.004733, 0.691367, 0.3039],
  ],
};

/** OKLab coordinates of a colour as seen with the given vision (DS-VIZ-02). */
export function perceived(rgb: Rgb8, vision: Vision): Lab {
  const linear = linearRgb(rgb);
  if (vision === "normal") {
    return linearToOklab(linear);
  }
  const clamp = (v: number): number => Math.min(1, Math.max(0, v));
  const project = (row: Lab): number =>
    clamp(row[0] * linear[0] + row[1] * linear[1] + row[2] * linear[2]);
  const [r0, r1, r2] = MACHADO[vision] as [Lab, Lab, Lab];
  return linearToOklab([project(r0), project(r1), project(r2)]);
}

export function deltaE(a: Rgb8, b: Rgb8, vision: Vision): number {
  const [la, aa, ba] = perceived(a, vision);
  const [lb, ab, bb] = perceived(b, vision);
  return 100 * Math.hypot(la - lb, aa - ab, ba - bb);
}

/** OKLab lightness recomputed from the 8-bit rendering, as DESIGN_SYSTEM §5.2 tabulates it. */
export function lightness(rgb: Rgb8): number {
  return linearToOklab(linearRgb(rgb))[0];
}

function declarations(css: string, selector: string): Map<string, string> {
  const start = css.indexOf(selector);
  if (start < 0) {
    throw new Error(`tokens.css has no block ${selector}`);
  }
  const open = css.indexOf("{", start);
  const close = css.indexOf("}", open);
  const body = css.slice(open + 1, close).replace(/\/\*[\s\S]*?\*\//g, "");
  const out = new Map<string, string>();
  for (const declaration of body.split(";")) {
    const colon = declaration.indexOf(":");
    const name = declaration.slice(0, colon).trim();
    if (colon > 0 && name.startsWith("--")) {
      out.set(name, declaration.slice(colon + 1).trim());
    }
  }
  return out;
}

const THEME_SELECTORS: Record<Theme, string> = {
  light: ':root,\n:root[data-theme="light"] {',
  dark: ':root[data-theme="dark"] {',
};

/** Theme tokens of `tokens.css` with the theme-independent aliases of the plain `:root` block. */
export function readTokens(path: string, theme: Theme): Tokens {
  const css = readFileSync(path, "utf8");
  const aliases = declarations(css, ":root {\n  /* Layout");
  const values = declarations(css, THEME_SELECTORS[theme]);
  return new Map([...aliases, ...values]);
}

/** Resolves `var(--x)` chains and renders the token in 8-bit sRGB. */
export function tokenRgb(tokens: Tokens, name: string): Rgb8 {
  let value = tokens.get(name);
  for (let depth = 0; value !== undefined && depth < 8; depth += 1) {
    const alias = ALIAS.exec(value);
    if (alias === null) {
      return oklchToRgb8(value);
    }
    value = tokens.get(alias[1] as string);
  }
  throw new Error(`token ${name} does not resolve to an oklch() value`);
}
