// Shared parts of the SF-14 role drawers (SCREENS_B §9.10 "Invite user", "Add role"; DESIGN_SYSTEM
// DS-CMP-09, DS-CMP-21, DS-CMP-29; PRD ERR-22; BUILD_SPEC WEB-19): repeatable rows of "Role" and "Scope"
// ("All entities" or "Selected entities" with a multi-select), their validation, and the live SoD
// conflict banner, an alert inserted after load whose "Request an exception" takes focus. The scope
// field offers what the grantor's own permission covers (rev 1.60; 04 T-PLT-10): nobody grants beyond
// their own access.
import { useEffect, useId, useRef } from "react";

import { Banner } from "../../components/feedback/Banner";
import { Field } from "../../components/form/Field";
import { MultiSelect } from "../../components/form/MultiSelect";
import { Select } from "../../components/form/Select";
import { Button } from "../../components/ui/Button";
import { WarningCircle, X } from "../../components/icons/registry";
import type { Scope } from "../../lib/access";
import type { Role, SodRule } from "../../lib/api/queries/roles";
import type { Entity } from "../../lib/api/queries/tenant";
import type { UserRoleGrant } from "../../lib/api/queries/users";
import { t } from "../../lib/i18n/t";

export interface RoleGrantDraft {
  readonly key: string;
  readonly roleId: string | null;
  readonly allEntities: boolean;
  readonly entityCodes: readonly string[];
}

let draftSerial = 0;

/** A new row; a grantor of named entities starts on "Selected entities", the one scope they may give. */
export function newGrantDraft(scope: Scope | null = "*"): RoleGrantDraft {
  draftSerial += 1;
  return {
    key: `grant-${String(draftSerial)}`,
    roleId: null,
    allEntities: scope === "*",
    entityCodes: [],
  };
}

/**
 * What the API found on the scope of one row (04 T-PLT-10): under the entities, under the scope. A form
 * reads the two from its placing of the refusal (docs/dev-guide.md DG-FE-06), so that the banner lists
 * what the row does not show.
 */
export interface ScopeFindings {
  readonly entities: string | null;
  readonly all: string | null;
}

export interface GrantErrors {
  readonly role: string | null;
  readonly entities: string | null;
}

/** The field errors of a row once a submit was attempted. */
export function grantErrors(draft: RoleGrantDraft, attempted: boolean): GrantErrors {
  if (!attempted) {
    return { role: null, entities: null };
  }
  return {
    role: draft.roleId === null ? t("access.roleFields.roleRequired") : null,
    entities:
      !draft.allEntities && draft.entityCodes.length === 0
        ? t("access.roleFields.entitiesRequired")
        : null,
  };
}

export function grantsValid(drafts: readonly RoleGrantDraft[]): boolean {
  return drafts.every((draft) => {
    const errors = grantErrors(draft, true);
    return errors.role === null && errors.entities === null;
  });
}

/** The API-S-UserRoleIn body of a valid row. */
export function toGrant(draft: RoleGrantDraft): UserRoleGrant {
  return {
    role_id: draft.roleId ?? "",
    is_all_entities: draft.allEntities,
    ...(draft.allEntities ? {} : { entity_codes: [...draft.entityCodes] }),
  };
}

/** PRD ERR-22 copy: "Separation of duties conflict <rule>: <description>." */
export function conflictMessage(rule: Pick<SodRule, "code" | "name">): string {
  return t("access.sod.conflict", { rule: rule.code, description: rule.name });
}

export interface RoleGrantRowsProps {
  readonly drafts: readonly RoleGrantDraft[];
  readonly onChange: (drafts: readonly RoleGrantDraft[]) => void;
  readonly roles: readonly Role[];
  readonly entities: readonly Entity[];
  /** The entities the grantor's own permission covers: what the scope field may offer. */
  readonly scope: Scope | null;
  /** The API's findings on the scope of the row at `index`. */
  readonly findings: (index: number) => ScopeFindings;
  readonly attempted: boolean;
  /** "Add another role" and "Remove role" (the invite drawer); a single row otherwise. */
  readonly repeatable: boolean;
}

export function RoleGrantRows({
  drafts,
  onChange,
  roles,
  entities,
  scope,
  findings,
  attempted,
  repeatable,
}: RoleGrantRowsProps) {
  const roleOptions = roles.map((role) => ({ value: role.id, label: role.name }));
  const named = scope !== "*";
  const entityOptions = entities
    .filter((entity) => scope === "*" || scope?.includes(entity.id) === true)
    .map((entity) => ({ value: entity.code, label: `${entity.code} · ${entity.name}` }));
  const update = (key: string, patch: Partial<RoleGrantDraft>) => {
    onChange(drafts.map((draft) => (draft.key === key ? { ...draft, ...patch } : draft)));
  };
  return (
    <div className="flex flex-col gap-4">
      {drafts.map((draft, index) => {
        const errors = grantErrors(draft, attempted);
        return (
          <GrantRow
            key={draft.key}
            draft={draft}
            index={index}
            errors={errors}
            found={findings(index)}
            named={named}
            roleOptions={roleOptions}
            entityOptions={entityOptions}
            removable={repeatable && drafts.length > 1}
            onChange={(patch) => {
              update(draft.key, patch);
            }}
            onRemove={() => {
              onChange(drafts.filter((candidate) => candidate.key !== draft.key));
            }}
          />
        );
      })}
      {repeatable ? (
        <div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              onChange([...drafts, newGrantDraft(scope)]);
            }}
          >
            {t("access.roleFields.addRole")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

interface GrantRowProps {
  readonly draft: RoleGrantDraft;
  readonly index: number;
  readonly errors: GrantErrors;
  readonly found: ScopeFindings;
  /** The grantor holds the permission for named entities only: "All entities" is not theirs to give. */
  readonly named: boolean;
  readonly roleOptions: readonly { readonly value: string; readonly label: string }[];
  readonly entityOptions: readonly { readonly value: string; readonly label: string }[];
  readonly removable: boolean;
  readonly onChange: (patch: Partial<RoleGrantDraft>) => void;
  readonly onRemove: () => void;
}

function GrantRow({
  draft,
  index,
  errors,
  found,
  named,
  roleOptions,
  entityOptions,
  removable,
  onChange,
  onRemove,
}: GrantRowProps) {
  const legendId = useId();
  const scopeNoteId = useId();
  const scopeErrorId = useId();
  const suffix = String(index + 1);
  const entitiesError = errors.entities ?? found.entities;
  return (
    <div
      role="group"
      aria-label={t("access.roleFields.rowLabel", { position: suffix })}
      className="flex flex-col gap-3 rounded-md border border-hairline p-3"
    >
      <div className="flex items-end gap-3">
        <div className="min-w-0 flex-1">
          <Field
            name={`role-${draft.key}`}
            label={t("access.roleFields.role")}
            required
            error={errors.role}
          >
            {(control) => (
              <Select
                control={control}
                options={roleOptions}
                value={draft.roleId}
                placeholder={t("access.roleFields.rolePlaceholder")}
                invalid={errors.role !== null}
                onChange={(value) => {
                  onChange({ roleId: value });
                }}
              />
            )}
          </Field>
        </div>
        {removable ? (
          <Button
            variant="ghost"
            icon={X}
            aria-label={t("access.roleFields.removeRole", { position: suffix })}
            onClick={onRemove}
          />
        ) : null}
      </div>
      <fieldset
        className="flex flex-col gap-2"
        aria-describedby={
          [found.all === null ? null : scopeErrorId, named ? scopeNoteId : null]
            .filter((id) => id !== null)
            .join(" ") || undefined
        }
      >
        <legend id={legendId} className="text-body-sm font-medium text-fg-1">
          {t("access.roleFields.scope")}
        </legend>
        <div className="flex flex-wrap gap-4">
          {named ? null : (
            <label className="flex items-center gap-2 text-body-sm text-fg-1">
              <input
                type="radio"
                name={`scope-${draft.key}`}
                checked={draft.allEntities}
                onChange={() => {
                  onChange({ allEntities: true, entityCodes: [] });
                }}
              />
              {t("access.roleFields.scopeAll")}
            </label>
          )}
          <label className="flex items-center gap-2 text-body-sm text-fg-1">
            <input
              type="radio"
              name={`scope-${draft.key}`}
              checked={!draft.allEntities}
              onChange={() => {
                onChange({ allEntities: false });
              }}
            />
            {t("access.roleFields.scopeSelected")}
          </label>
        </div>
        {found.all === null ? null : (
          <p id={scopeErrorId} className="flex items-start gap-1 text-body-sm text-negative-fg">
            <WarningCircle aria-hidden="true" className="mt-0.5 shrink-0" />
            {found.all}
          </p>
        )}
        {named ? (
          <p id={scopeNoteId} className="text-body-sm text-fg-2">
            {t("access.roleFields.ownScope")}
          </p>
        ) : null}
      </fieldset>
      {draft.allEntities ? null : (
        <Field
          name={`entities-${draft.key}`}
          label={t("access.roleFields.entities")}
          required
          error={entitiesError}
        >
          {(control) => (
            <MultiSelect
              control={control}
              options={entityOptions}
              values={draft.entityCodes}
              invalid={entitiesError !== null}
              onChange={(values) => {
                onChange({ entityCodes: values });
              }}
            />
          )}
        </Field>
      )}
    </div>
  );
}

export interface SodConflictBannerProps {
  readonly rules: readonly SodRule[];
  /** "Request an exception"; the first conflict's action takes focus when the banner appears. */
  readonly onRequestException: (rule: SodRule) => void;
  readonly testId?: string | undefined;
}

/** The ERR-22 alert of the live SoD check, one banner per conflicting rule. */
export function SodConflictBanner({ rules, onRequestException, testId }: SodConflictBannerProps) {
  const first = useRef<HTMLButtonElement>(null);
  const codes = rules.map((rule) => rule.code).join(",");
  useEffect(() => {
    if (codes !== "") {
      first.current?.focus();
    }
  }, [codes]);
  if (rules.length === 0) {
    return null;
  }
  return (
    <div data-testid={testId ?? "SF-14-banner-sod-conflict"} className="flex flex-col gap-2">
      {rules.map((rule, index) => (
        <Banner
          key={rule.code}
          tone="negative"
          title={conflictMessage(rule)}
          actions={
            <Button
              {...(index === 0 ? { ref: first } : {})}
              variant="link"
              size="sm"
              onClick={() => {
                onRequestException(rule);
              }}
            >
              {t("access.sod.requestException")}
            </Button>
          }
        />
      ))}
    </div>
  );
}
