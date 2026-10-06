// ESLint flat configuration (docs/dev-guide.md DG-FE-17): typescript-eslint strict,
// react-hooks and jsx-a11y recommended rules.
import { readFileSync } from "node:fs";

import js from "@eslint/js";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

const BUSINESS_DATE_MESSAGE =
  "Business dates stay YYYY-MM-DD strings; construct dates only in src/lib/format (DG-FE-20).";
// DG-FE-20: `Date.now()` stays allowed for durations and timers.
const BUSINESS_DATE_SELECTORS = [
  { selector: "NewExpression[callee.name='Date']", message: BUSINESS_DATE_MESSAGE },
  {
    selector: "CallExpression[callee.object.name='Date'][callee.property.name='parse']",
    message: BUSINESS_DATE_MESSAGE,
  },
];
const IDEMPOTENCY_KEY_MESSAGE =
  "A command's Idempotency-Key comes from src/lib/api/commands.ts: useCommand, or the CommandKeys of useCommandKeys (DG-FE-05).";
// DG-FE-05 (rev 1.156): a key made where the command is sent is a new key on every press, so a lost
// response followed by a second press runs the command twice. The header as an object key, as the
// name given to `Headers.set` or `append`, assigned to a member, and as the name of a
// `[name, value]` pair.
const IDEMPOTENCY_KEY_SELECTORS = [
  { selector: "Property[key.value='Idempotency-Key']", message: IDEMPOTENCY_KEY_MESSAGE },
  {
    selector:
      "CallExpression[callee.property.name=/^(set|append)$/][arguments.0.value='Idempotency-Key']",
    message: IDEMPOTENCY_KEY_MESSAGE,
  },
  {
    selector: "AssignmentExpression > MemberExpression.left[property.value='Idempotency-Key']",
    message: IDEMPOTENCY_KEY_MESSAGE,
  },
  {
    selector: "ArrayExpression[elements.length=2][elements.0.value='Idempotency-Key']",
    message: IDEMPOTENCY_KEY_MESSAGE,
  },
];
const ACCESS_MESSAGE =
  "The member's permissions are read in src/lib/access.ts: ask holds, holdsAnywhere, holdsForAll or holdsForEvery for the entities a permission covers (DG-FE-16).";
// DG-FE-16 (rev 1.175): a role is granted for all entities or for named ones, so whether a code is
// among `permissions` does not say whether a command may be used on a record. `.includes` on the
// member's permissions, and any read of `permission_scopes`.
const ACCESS_SELECTORS = [
  {
    selector:
      "CallExpression[callee.property.name='includes'][callee.object.property.name='permissions']",
    message: ACCESS_MESSAGE,
  },
  {
    selector: "CallExpression[callee.property.name='includes'][callee.object.name='permissions']",
    message: ACCESS_MESSAGE,
  },
  { selector: "MemberExpression[property.name='permission_scopes']", message: ACCESS_MESSAGE },
];
const REFUSAL_MESSAGE =
  "The field-error map of a refused command is read in src/lib/api only: a form places the errors with src/lib/api/refusals.ts and shows RefusalBanner, which says what no field took (DG-FE-06).";
// DG-FE-06 (rev 1.228): a banner shown only while the map is empty shows nothing when the refusal
// names a member the form has no field for, and the gate is written in more ways than a selector on
// one of them catches — on the member, through `fieldErrorsOf`, through an alias, through a spread.
// So the map is not read at all outside the API library: `.fieldErrors` as a member, `fieldErrorsOf`
// as a call, and `fieldErrors` taken out of an object by destructuring.
const REFUSAL_SELECTORS = [
  { selector: "MemberExpression[property.name='fieldErrors']", message: REFUSAL_MESSAGE },
  { selector: "CallExpression[callee.name='fieldErrorsOf']", message: REFUSAL_MESSAGE },
  { selector: "ObjectPattern > Property[key.name='fieldErrors']", message: REFUSAL_MESSAGE },
];
// The files that still ask `permissions.includes` (item W-12c converts them by family), in
// `config/bare-permission-gates.json`. A ratchet: the list only shrinks.
// `config/eslint-access.test.ts` fails when a listed file no longer writes a bare gate, and when a
// file joins the list.
const BARE_PERMISSION_GATES = JSON.parse(
  readFileSync(new URL("./config/bare-permission-gates.json", import.meta.url), "utf8"),
);
// The files that still read the field-error map, in `config/field-error-readers.json` (the second
// head of KIT-UNPLACED-ERRORS-1 and KIT-REFUSAL-SENTENCES-2 convert them). A ratchet as the one
// above: `config/eslint-refusals.test.ts` fails when a listed file no longer reads the map, and when
// a file joins the list.
const FIELD_ERROR_READERS = JSON.parse(
  readFileSync(new URL("./config/field-error-readers.json", import.meta.url), "utf8"),
);
const EVERY_SELECTOR = [
  ...BUSINESS_DATE_SELECTORS,
  ...IDEMPOTENCY_KEY_SELECTORS,
  ...ACCESS_SELECTORS,
  ...REFUSAL_SELECTORS,
];
/** The rule with every selector but those of the families named. */
const restricted = (...dropped) => [
  "error",
  ...EVERY_SELECTOR.filter((selector) => !dropped.some((family) => family.includes(selector))),
];
const TESTS = ["**/src/**/*.test.{ts,tsx}", "**/src/test/**/*.{ts,tsx}"];
const IN_BOTH_RATCHETS = FIELD_ERROR_READERS.filter((file) => BARE_PERMISSION_GATES.includes(file));

export default tseslint.config(
  { ignores: ["**/dist/**", "**/node_modules/**", "**/e2e/.screens/**", "**/e2e/.results/**"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.strict, jsxA11y.flatConfigs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "no-restricted-syntax": ["error", ...BUSINESS_DATE_SELECTORS],
    },
  },
  {
    // `make lint` passes --config, so patterns resolve from the repository root; `**/` covers both.
    // The product's source: the four rules. The e2e suite sends commands to the API as a client of
    // its own and keeps the first rule only.
    files: ["**/src/**/*.{ts,tsx}"],
    rules: { "no-restricted-syntax": restricted() },
  },
  {
    // A test states the member it signs in and the map a problem makes.
    files: TESTS,
    rules: { "no-restricted-syntax": restricted(ACCESS_SELECTORS, REFUSAL_SELECTORS) },
  },
  {
    // Not gates: the access module answers the question; the files of the ratchet are not
    // converted yet.
    files: ["**/src/lib/access.ts", ...BARE_PERMISSION_GATES.map((file) => `**/${file}`)],
    ignores: TESTS,
    rules: { "no-restricted-syntax": restricted(ACCESS_SELECTORS) },
  },
  {
    files: ["**/src/lib/format/**/*.{ts,tsx}"],
    rules: { "no-restricted-syntax": restricted(BUSINESS_DATE_SELECTORS) },
  },
  {
    // The API library makes the map and places it; the files of the second ratchet still read it.
    files: ["**/src/lib/api/**/*.{ts,tsx}", ...FIELD_ERROR_READERS.map((file) => `**/${file}`)],
    ignores: TESTS,
    rules: { "no-restricted-syntax": restricted(REFUSAL_SELECTORS) },
  },
  // A file of both ratchets (a block without files is refused, so none is written for none).
  ...(IN_BOTH_RATCHETS.length === 0
    ? []
    : [
        {
          files: IN_BOTH_RATCHETS.map((file) => `**/${file}`),
          rules: { "no-restricted-syntax": restricted(ACCESS_SELECTORS, REFUSAL_SELECTORS) },
        },
      ]),
  {
    files: ["**/src/lib/api/commands.ts"],
    rules: { "no-restricted-syntax": restricted(IDEMPOTENCY_KEY_SELECTORS, REFUSAL_SELECTORS) },
  },
);
