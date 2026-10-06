// Message catalogue (docs/dev-guide.md DG-FE-11; DESIGN_SYSTEM DS-I18N-01, DS-I18N-06). A small
// in-house helper over native Intl: flat `<area>.<screen>.<element>` keys, named placeholders, and
// plural variants `<key>.<category>` selected with Intl.PluralRules from a numeric `count`.
import messages from "../../messages/en.json";
import { pluralCategory } from "./plural";
import { accentTemplate, padPseudo, PLACEHOLDER, pseudoRequested } from "./pseudo";

export type MessageParams = Readonly<Record<string, string | number>>;

/** The language of catalogue strings; 1.0 ships `en` (DS-I18N-02 `ui_locale`). */
export const UI_LOCALE = "en";

const CATALOGUE: Readonly<Record<string, string>> = messages;

// Pseudo-localisation is a review aid of development and e2e builds (the gallery flag is set for
// both); a production build ignores `?pseudo=1`.
const PSEUDO_AVAILABLE =
  import.meta.env.DEV ||
  import.meta.env.MODE === "test" ||
  import.meta.env.VITE_EREV_DESIGN_GALLERY === "1";

// A missing key or parameter is a defect: it throws in development and tests, and a production
// build shows the key rather than failing the screen.
const STRICT = import.meta.env.DEV || import.meta.env.MODE === "test";

const config = { pseudo: false };

export function configureI18n(options: { readonly search: string }): void {
  config.pseudo = PSEUDO_AVAILABLE && pseudoRequested(options.search);
}

function template(key: string, params: MessageParams): string | undefined {
  const count = params.count;
  if (typeof count === "number") {
    return CATALOGUE[`${key}.${pluralCategory(UI_LOCALE, count)}`] ?? CATALOGUE[`${key}.other`];
  }
  return CATALOGUE[key];
}

function interpolate(text: string, params: MessageParams, key: string): string {
  return text.replace(PLACEHOLDER, (placeholder: string, name: string) => {
    const value = params[name];
    if (value === undefined) {
      if (STRICT) {
        throw new Error(`Message ${key} needs the parameter ${name}`);
      }
      return placeholder;
    }
    return String(value);
  });
}

/** Whether the catalogue holds `key`, for labels that fall back to text when it does not. */
export function hasMessage(key: string): boolean {
  return CATALOGUE[key] !== undefined;
}

export function t(key: string, params: MessageParams = {}): string {
  const text = template(key, params);
  if (text === undefined) {
    if (STRICT) {
      throw new Error(`Missing message key: ${key}`);
    }
    return key;
  }
  const plain = interpolate(text, params, key);
  return config.pseudo ? padPseudo(interpolate(accentTemplate(text), params, key), plain) : plain;
}
