// Pseudo-localisation (DESIGN_SYSTEM DS-I18N-06): catalogue text renders with accented letters and at
// least 35% padding, so hard-coded strings and layouts that cannot take longer text show up in
// review. Placeholders stay intact and interpolated values are not accented.
export const PLACEHOLDER = /\{([A-Za-z_][A-Za-z0-9_]*)\}/g;
export const PSEUDO_EXPANSION = 0.35;

const ACCENTS: Readonly<Record<string, string>> = {
  a: "à",
  b: "ƀ",
  c: "ç",
  d: "ð",
  e: "é",
  f: "ƒ",
  g: "ĝ",
  h: "ĥ",
  i: "î",
  j: "ĵ",
  k: "ķ",
  l: "ļ",
  m: "ɱ",
  n: "ñ",
  o: "ö",
  p: "þ",
  q: "ǫ",
  r: "ŕ",
  s: "š",
  t: "ţ",
  u: "û",
  v: "ṽ",
  w: "ŵ",
  x: "ẋ",
  y: "ý",
  z: "ž",
  A: "À",
  B: "Ɓ",
  C: "Ç",
  D: "Ð",
  E: "É",
  F: "Ƒ",
  G: "Ĝ",
  H: "Ĥ",
  I: "Î",
  J: "Ĵ",
  K: "Ķ",
  L: "Ļ",
  M: "Ṁ",
  N: "Ñ",
  O: "Ö",
  P: "Þ",
  Q: "Ǫ",
  R: "Ŕ",
  S: "Š",
  T: "Ţ",
  U: "Û",
  V: "Ṽ",
  W: "Ŵ",
  X: "Ẋ",
  Y: "Ý",
  Z: "Ž",
};

function accent(text: string): string {
  return Array.from(text, (char) => ACCENTS[char] ?? char).join("");
}

/** Accents a catalogue template outside its `{placeholders}`. */
export function accentTemplate(template: string): string {
  let result = "";
  let last = 0;
  for (const match of template.matchAll(PLACEHOLDER)) {
    result += accent(template.slice(last, match.index)) + match[0];
    last = match.index + match[0].length;
  }
  return result + accent(template.slice(last));
}

/** Brackets and pads accented text so it is at least 35% longer than the plain text. */
export function padPseudo(accented: string, plain: string): string {
  const extra = Math.max(2, Math.ceil(plain.length * PSEUDO_EXPANSION));
  return `[${accented}${"·".repeat(extra - 2)}]`;
}

export function pseudoRequested(search: string): boolean {
  return new URLSearchParams(search).get("pseudo") === "1";
}
