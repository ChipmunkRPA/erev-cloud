// SF-15:entities Entities (SCREENS_B §9.2; SCREENS §0.4 RT-75, §0.5 SCR-URL `drawer`, `row`, §0.7
// SCR-ST-03, SCR-ST-09, SCR-PERM-01, SCR-PERM-02; DESIGN_SYSTEM DS-CMP-09, DS-CMP-10, DS-CMP-21, DS-CMP-23;
// 04 API-R-17 `GET, POST /entities`, `PATCH /entities/{id}` (`If-Match`), `PUT /entities/{id}/books/{code}`,
// `GET /books`, API-R-18 `GET /calendars`, API-R-19 `GET /tenant-currencies`; BR-REF-01; REQ-REF-001;
// BUILD_SPEC RFD-18). The Settings frame with the Workspace route tabs and the DataGrid "Entities" (code,
// name, country, functional currency, time zone, calendar linking SF-15:calendars, parent, books,
// active). A code opens "Edit <code>" and "New entity" the create drawer (`masterdata.maintain` or
// `settings.manage`; read-only for other `config.read` holders). The drawer saves the entity, then each
// changed book through `PUT /entities/{id}/books/{code}`. The API refuses a currency or time-zone change
// once postings exist (ERR-41 `immutable-record`); API-S-Entity carries no posting flag, so the lock is
// reported from the refusal rather than drawn ahead of it.
import { useQuery } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useId, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import { type GridColumn, type GridSource } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { Combobox } from "../../components/form/Combobox";
import { controlClass, Field } from "../../components/form/Field";
import { Select } from "../../components/form/Select";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import {
  type Calendar,
  calendarRoute,
  CALENDARS_ROUTE,
  useCalendars,
} from "../../lib/api/queries/calendars";
import { enabledCurrencyCodes, useTenantCurrencies } from "../../lib/api/queries/currencies";
import {
  BOOK_CODES,
  bookLabel,
  enabledBookLabels,
  ENTITY_CODE_PATTERN,
  ENTITY_MAINTAIN_PERMISSIONS,
  entitiesGridKey,
  entityBook,
  entityBookPath,
  type EntityBookUpdate,
  type EntityCreate,
  entityPath,
  type EntityUpdate,
  EVERY_ENTITY,
  fetchEntitiesPage,
  useAllEntities,
} from "../../lib/api/queries/entities";
import { useMe } from "../../lib/api/queries/me";
import {
  type Book,
  type BookCode,
  booksKey,
  type Entity,
  ENTITIES_PATH,
  fetchBooks,
  rowIfMatch,
  STRUCTURE_READ_PERMISSION,
} from "../../lib/api/queries/tenant";
import { fieldMessages, useFieldRefusals } from "../../lib/api/refusals";
import { formatNumber, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { countryOptions, timeZoneOptions } from "../../lib/reference/countries";
import { SettingsPageHeader, useBuiltPaths } from "./index";

const DRAWER_ENTITY = "entity";
/** PRD ERR-41: the API refuses a change to a field frozen by the first posting. */
const IMMUTABLE_SLUG = "immutable-record";

function mono(text: string | null) {
  return text === null ? (
    <span className="text-fg-3">{NO_VALUE}</span>
  ) : (
    <span className="font-mono text-mono text-fg-2">{text}</span>
  );
}

function yesNo(value: boolean): string {
  return t(value ? "settings.entities.yes" : "settings.entities.no");
}

/** SCREENS_B §9.2 grid columns. */
export function entityColumns(
  calendars: ReadonlyMap<string, Calendar>,
  entities: ReadonlyMap<string, Entity>,
  books: readonly Book[],
  calendarsBuilt: boolean,
): readonly GridColumn<Entity>[] {
  return [
    {
      id: "code",
      header: t("settings.entities.column.code"),
      kind: "identifier",
      value: (entity) => entity.code,
      href: (entity) => `?drawer=${DRAWER_ENTITY}&row=${entity.id}`,
      sortKey: "code",
      width: 120,
    },
    {
      id: "name",
      header: t("settings.entities.column.name"),
      kind: "text",
      value: (entity) => entity.name,
      sortKey: "name",
      width: 260,
    },
    {
      id: "country_code",
      header: t("settings.entities.column.country"),
      kind: "text",
      value: (entity) => entity.country_code,
      render: (entity) => mono(entity.country_code),
      width: 96,
    },
    {
      id: "functional_currency",
      header: t("settings.entities.column.functionalCurrency"),
      kind: "text",
      value: (entity) => entity.functional_currency,
      render: (entity) => mono(entity.functional_currency),
      width: 168,
    },
    {
      id: "time_zone",
      header: t("settings.entities.column.timeZone"),
      kind: "text",
      value: (entity) => entity.time_zone,
      width: 184,
    },
    {
      id: "calendar",
      header: t("settings.entities.column.calendar"),
      kind: "text",
      value: (entity) => calendars.get(entity.calendar_id)?.code ?? null,
      render: (entity) => {
        const code = calendars.get(entity.calendar_id)?.code ?? null;
        if (code === null) {
          return mono(null);
        }
        return calendarsBuilt ? (
          <Link
            to={calendarRoute(code)}
            className="font-mono text-mono text-accent-fg hover:underline"
          >
            {code}
          </Link>
        ) : (
          mono(code)
        );
      },
      width: 128,
    },
    {
      id: "parent",
      header: t("settings.entities.column.parent"),
      kind: "text",
      value: (entity) =>
        entity.parent_entity_id === null
          ? null
          : (entities.get(entity.parent_entity_id)?.code ?? entity.parent_entity_id),
      render: (entity) =>
        mono(
          entity.parent_entity_id === null
            ? null
            : (entities.get(entity.parent_entity_id)?.code ?? entity.parent_entity_id),
        ),
      width: 128,
    },
    {
      id: "books",
      header: t("settings.entities.column.books"),
      kind: "text",
      value: (entity) => enabledBookLabels(entity, books).join(", "),
      width: 176,
    },
    {
      id: "is_active",
      header: t("settings.entities.column.active"),
      kind: "text",
      value: (entity) => yesNo(entity.is_active),
      width: 88,
    },
  ];
}

export function EntitiesScreen() {
  const me = useMe();
  const access = useAccess();
  const title = t("settings.entities.title");

  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={6} />;
  } else if (!access.holdsAnywhere(STRUCTURE_READ_PERMISSION)) {
    body = (
      <EmptyState
        title={t("settings.access.title", { area: title })}
        description={t("settings.access.description", {
          permission: t("settings.access.permission.configRead"),
        })}
      />
    );
  } else {
    return (
      <EntitiesPage
        maintain={ENTITY_MAINTAIN_PERMISSIONS.some((permission) =>
          access.holdsAnywhere(permission),
        )}
      />
    );
  }
  return (
    <div
      data-testid="SF-15-entities-page"
      className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="workspace" />
      {body}
    </div>
  );
}

function EntitiesPage({ maintain }: { readonly maintain: boolean }) {
  const [params, setParams] = useSearchParams();
  const built = useBuiltPaths();
  const [total, setTotal] = useState<number | undefined>(undefined);
  const title = t("settings.entities.title");
  const calendars = useCalendars();
  const books = useQuery({ queryKey: booksKey(), queryFn: fetchBooks });
  const entities = useAllEntities();
  const calendarMap = useMemo(
    () => new Map((calendars.data ?? []).map((calendar) => [calendar.id, calendar])),
    [calendars.data],
  );
  const entityMap = useMemo(
    () => new Map((entities.data ?? []).map((entity) => [entity.id, entity])),
    [entities.data],
  );
  const calendarsBuilt = built.has(CALENDARS_ROUTE);
  const columns = useMemo(
    () => entityColumns(calendarMap, entityMap, books.data ?? [], calendarsBuilt),
    [calendarMap, entityMap, books.data, calendarsBuilt],
  );
  const source: GridSource<Entity> = {
    queryKey: entitiesGridKey(),
    fetchPage: fetchEntitiesPage,
  };
  const drawer = params.get("drawer");
  const row = params.get("row");
  const openDrawer = (id: string | null) => {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.set("drawer", DRAWER_ENTITY);
        if (id === null) {
          next.delete("row");
        } else {
          next.set("row", id);
        }
        return next;
      },
      { replace: true },
    );
  };
  const closeDrawer = () => {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.delete("drawer");
        next.delete("row");
        return next;
      },
      { replace: true },
    );
  };
  const newEntity = maintain
    ? { label: t("settings.entities.new"), onAction: () => openDrawer(null) }
    : undefined;
  const countLabel = (value: number, formatted: string) =>
    t("settings.entities.count", { count: value, formatted });
  const selected = row === null ? null : (entityMap.get(row) ?? null);

  return (
    <div
      data-testid="SF-15-entities-page"
      className="flex h-full min-h-0 w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="workspace">
        {total === undefined ? null : (
          <p className="num text-body-sm text-fg-3">
            {countLabel(total, formatNumber(total, { kind: "count" }))}
          </p>
        )}
      </SettingsPageHeader>
      <div className="flex min-h-0 flex-1 flex-col">
        <DataGrid<Entity>
          name="entities"
          title={t("settings.entities.grid")}
          errorTitle={t("settings.entities.loadError")}
          countLabel={countLabel}
          columns={columns}
          source={source}
          rowKey={(entity) => entity.id}
          rowLabel={(entity) => entity.code}
          testIdPrefix="SF-15"
          rowTestKey={(entity) => entity.code}
          onTotalChange={(next) => setTotal(next?.count)}
          toolbarActions={
            newEntity === undefined ? undefined : (
              <Button variant="primary" onClick={newEntity.onAction}>
                {newEntity.label}
              </Button>
            )
          }
          emptyState={
            <div data-testid="SF-15-empty-entities">
              <EmptyState
                title={t("settings.entities.empty.title")}
                description={t("settings.entities.empty.description")}
                action={newEntity}
              />
            </div>
          }
        />
      </div>
      {drawer === DRAWER_ENTITY && (row === null || selected !== null) ? (
        <EntityDrawer
          entity={selected}
          readOnly={!maintain}
          calendars={calendars.data ?? []}
          books={books.data ?? []}
          entities={entities.data ?? []}
          onClose={closeDrawer}
          onCreated={(id) => openDrawer(id)}
        />
      ) : null}
    </div>
  );
}

interface EntityDrawerProps {
  /** null creates. */
  readonly entity: Entity | null;
  readonly readOnly: boolean;
  readonly calendars: readonly Calendar[];
  readonly books: readonly Book[];
  readonly entities: readonly Entity[];
  readonly onClose: () => void;
  /** After a create the drawer reopens on the new entity so its books can be enabled. */
  readonly onCreated: (id: string) => void;
}

interface BookDraft {
  readonly enabled: boolean;
  readonly firstPeriodKey: string;
}

function bookDrafts(entity: Entity | null): Readonly<Record<BookCode, BookDraft>> {
  const draft = (code: BookCode): BookDraft => {
    const row = entity === null ? null : entityBook(entity, code);
    return {
      enabled: row?.is_enabled ?? (entity === null && code === "ASC606"),
      firstPeriodKey: row?.first_period_key ?? "",
    };
  };
  return { ASC606: draft("ASC606"), IFRS15: draft("IFRS15"), LEGACY: draft("LEGACY") };
}

/**
 * The API members the fields of the entity drawer send (DG-FE-06 rev 1.228). "New entity" sends the
 * first period of its ASC 606 book with the entity. "Edit" sends neither the code, nor the calendar,
 * nor a book: a book is a command of its own, and what it is refused for stands at its row.
 */
const ENTITY_MEMBERS = {
  code: ["code"],
  name: ["name"],
  country_code: ["country_code"],
  functional_currency: ["functional_currency"],
  time_zone: ["time_zone"],
  calendar_id: ["calendar_id"],
  parent_entity_id: ["parent_entity_id"],
  tax_id: ["tax_id"],
  "books.ASC606": ["first_period_key"],
  "books.IFRS15": [],
  "books.LEGACY": [],
} as const;
type EntityField = keyof typeof ENTITY_MEMBERS;
type EntityMembers = Readonly<Record<EntityField, readonly string[]>>;
const ENTITY_MEMBERS_OF_EDIT: EntityMembers = {
  ...ENTITY_MEMBERS,
  code: [],
  calendar_id: [],
  "books.ASC606": [],
};
const NO_ENTITY_MEMBER: EntityMembers = {
  code: [],
  name: [],
  country_code: [],
  functional_currency: [],
  time_zone: [],
  calendar_id: [],
  parent_entity_id: [],
  tax_id: [],
  "books.ASC606": [],
  "books.IFRS15": [],
  "books.LEGACY": [],
};
const BOOK_ROW_MEMBERS = ["is_enabled", "first_period_key"] as const;
const BOOK_MEMBERS: Readonly<Record<BookCode, EntityMembers>> = {
  ASC606: { ...NO_ENTITY_MEMBER, "books.ASC606": BOOK_ROW_MEMBERS },
  IFRS15: { ...NO_ENTITY_MEMBER, "books.IFRS15": BOOK_ROW_MEMBERS },
  LEGACY: { ...NO_ENTITY_MEMBER, "books.LEGACY": BOOK_ROW_MEMBERS },
};

/** SCREENS_B §9.2 "New entity" / "Edit <code>" drawer. */
export function EntityDrawer({
  entity,
  readOnly,
  calendars,
  books,
  entities,
  onClose,
  onCreated,
}: EntityDrawerProps) {
  const toast = useToast();
  const formId = useId();
  const activeId = useId();
  const currencies = useTenantCurrencies();
  const [code, setCode] = useState(entity?.code ?? "");
  const [name, setName] = useState(entity?.name ?? "");
  const [country, setCountry] = useState<string | null>(entity?.country_code ?? null);
  const [currency, setCurrency] = useState<string | null>(entity?.functional_currency ?? null);
  const [timeZone, setTimeZone] = useState<string | null>(entity?.time_zone ?? null);
  const [calendarId, setCalendarId] = useState<string | null>(entity?.calendar_id ?? null);
  const [parentId, setParentId] = useState<string | null>(entity?.parent_entity_id ?? null);
  const [taxId, setTaxId] = useState(entity?.tax_id ?? "");
  const [active, setActive] = useState(entity?.is_active ?? true);
  const [drafts, setDrafts] = useState(() => bookDrafts(entity));
  const [local, setLocal] = useState<Readonly<Record<string, string>>>({});
  const invalidates = [EVERY_ENTITY];
  const create = useCommand<Entity>({ method: "POST", path: ENTITIES_PATH, invalidates });
  const edit = useCommand<Entity>({
    method: "PATCH",
    path: entity === null ? ENTITIES_PATH : entityPath(entity.id),
    invalidates,
  });
  const bookCommands = {
    ASC606: useCommand({
      method: "PUT",
      path: entity === null ? ENTITIES_PATH : entityBookPath(entity.id, "ASC606"),
      invalidates,
    }),
    IFRS15: useCommand({
      method: "PUT",
      path: entity === null ? ENTITIES_PATH : entityBookPath(entity.id, "IFRS15"),
      invalidates,
    }),
    LEGACY: useCommand({
      method: "PUT",
      path: entity === null ? ENTITIES_PATH : entityBookPath(entity.id, "LEGACY"),
      invalidates,
    }),
  } as const;
  const command = entity === null ? create : edit;
  // The entity's own refusal, else that of the first book refused: one command is refused at a time.
  const failedBook =
    command.problem === null
      ? (BOOK_CODES.find((bookCode) => bookCommands[bookCode].problem !== null) ?? null)
      : null;
  const problem =
    command.problem ?? (failedBook === null ? null : bookCommands[failedBook].problem);
  // A book that is switched off shows no field, so its refusal is the banner's.
  const refusals = useFieldRefusals<EntityField>(
    problem,
    failedBook !== null
      ? drafts[failedBook].enabled
        ? BOOK_MEMBERS[failedBook]
        : NO_ENTITY_MEMBER
      : entity === null
        ? ENTITY_MEMBERS
        : ENTITY_MEMBERS_OF_EDIT,
  );
  const immutable = command.problem?.type.endsWith(IMMUTABLE_SLUG) === true;
  const errors: Partial<Record<string, string>> = { ...fieldMessages(refusals.fields), ...local };
  if (immutable) {
    for (const field of ["functional_currency", "time_zone"]) {
      errors[field] ??= t("settings.entities.drawer.fixedAfterPosting");
    }
  }
  const pending = command.pending || BOOK_CODES.some((bookCode) => bookCommands[bookCode].pending);
  const currencyCodes = useMemo(() => {
    const codes = [...enabledCurrencyCodes(currencies.data ?? [])];
    if (currency !== null && !codes.includes(currency)) {
      codes.push(currency);
    }
    return codes;
  }, [currencies.data, currency]);
  const countries = useMemo(() => countryOptions(), []);
  const zones = useMemo(() => timeZoneOptions(entity?.time_zone ?? null), [entity?.time_zone]);
  const dirty =
    entity === null
      ? code !== "" || name !== ""
      : name !== entity.name ||
        (country ?? null) !== entity.country_code ||
        currency !== entity.functional_currency ||
        timeZone !== entity.time_zone ||
        parentId !== entity.parent_entity_id ||
        (taxId === "" ? null : taxId) !== entity.tax_id ||
        active !== entity.is_active ||
        BOOK_CODES.some((bookCode) => bookChanged(entity, bookCode, drafts[bookCode]));

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (readOnly || pending) {
      return;
    }
    const found: Record<string, string> = {};
    if (entity === null) {
      if (code.trim() === "") {
        found.code = t("settings.entities.drawer.codeRequired");
      } else if (!ENTITY_CODE_PATTERN.test(code.trim())) {
        found.code = t("settings.entities.drawer.codeRule");
      }
    }
    if (name.trim() === "") {
      found.name = t("settings.entities.drawer.nameRequired");
    }
    if (currency === null) {
      found.functional_currency = t("settings.entities.drawer.currencyRequired");
    }
    if (timeZone === null || timeZone === "") {
      found.time_zone = t("settings.entities.drawer.timeZoneRequired");
    }
    if (calendarId === null) {
      found.calendar_id = t("settings.entities.drawer.calendarRequired");
    }
    for (const bookCode of BOOK_CODES) {
      const draft = drafts[bookCode];
      if (draft.enabled && draft.firstPeriodKey.trim() === "") {
        found[`books.${bookCode}`] = t("settings.entities.drawer.firstPeriodRequired");
      }
    }
    setLocal(found);
    if (
      Object.keys(found).length > 0 ||
      currency === null ||
      timeZone === null ||
      calendarId === null
    ) {
      return;
    }
    if (entity === null) {
      const body: EntityCreate = {
        code: code.trim(),
        name: name.trim(),
        country_code: country,
        functional_currency: currency,
        time_zone: timeZone,
        calendar_id: calendarId,
        parent_entity_id: parentId,
        tax_id: taxId.trim() === "" ? null : taxId.trim(),
        is_active: active,
        first_period_key: drafts.ASC606.firstPeriodKey.trim(),
      };
      const outcome = await create.submit(body);
      if (outcome.kind === "succeeded" && outcome.data !== null) {
        toast.show({
          tone: "positive",
          message: t("settings.entities.drawer.saved", { code: outcome.data.code }),
        });
        onCreated(outcome.data.id);
      }
      return;
    }
    const patch: EntityUpdate = {
      ...(name.trim() !== entity.name ? { name: name.trim() } : {}),
      ...(country !== entity.country_code ? { country_code: country } : {}),
      ...(currency !== entity.functional_currency ? { functional_currency: currency } : {}),
      ...(timeZone !== entity.time_zone ? { time_zone: timeZone } : {}),
      ...(parentId !== entity.parent_entity_id ? { parent_entity_id: parentId } : {}),
      ...((taxId.trim() === "" ? null : taxId.trim()) !== entity.tax_id
        ? { tax_id: taxId.trim() === "" ? null : taxId.trim() }
        : {}),
      ...(active !== entity.is_active ? { is_active: active } : {}),
    };
    if (Object.keys(patch).length > 0) {
      const outcome = await edit.submit(patch, { ifMatch: rowIfMatch(entity.row_version) });
      if (outcome.kind !== "succeeded") {
        return;
      }
    }
    for (const bookCode of BOOK_CODES) {
      const draft = drafts[bookCode];
      if (!bookChanged(entity, bookCode, draft)) {
        continue;
      }
      const body: EntityBookUpdate = {
        is_enabled: draft.enabled,
        first_period_key: draft.firstPeriodKey.trim() === "" ? null : draft.firstPeriodKey.trim(),
      };
      const outcome = await bookCommands[bookCode].submit(body);
      if (outcome.kind !== "succeeded") {
        return;
      }
    }
    toast.show({
      tone: "positive",
      message: t("settings.entities.drawer.saved", { code: entity.code }),
    });
    onClose();
  };

  // A record that is fixed after its first posting says so at the two fields it fixes.
  const problemBanner =
    command.banner !== null || (refusals.banner !== null && !immutable) ? (
      <RefusalBanner problem={refusals.banner} placed={refusals.placed} conflict={command.banner} />
    ) : undefined;
  const parents = entities.filter((candidate) => candidate.id !== entity?.id);
  const field = (control: { readonly id: string; readonly name: string }, invalid: boolean) =>
    `${controlClass(invalid)}${control.name === "code" ? " font-mono" : ""}`;

  return (
    <Drawer
      open
      title={
        entity === null
          ? t("settings.entities.drawer.newTitle")
          : t("settings.entities.drawer.editTitle", { code: entity.code })
      }
      subtitle={entity?.name}
      dirty={dirty && !readOnly}
      submitting={pending}
      banner={problemBanner}
      primaryAction={
        readOnly ? undefined : { label: t("settings.entities.drawer.save"), form: formId }
      }
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-15-drawer-entity"
        onSubmit={(event) => void submit(event)}
        className="flex flex-col gap-4"
      >
        <Field
          name="code"
          label={t("settings.entities.drawer.code")}
          required={entity === null}
          error={errors.code ?? null}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              readOnly={entity !== null || readOnly}
              value={code}
              onChange={(event) => {
                setCode(event.target.value);
                refusals.edited("code");
              }}
              className={field(control, errors.code !== undefined)}
            />
          )}
        </Field>
        <Field
          name="name"
          label={t("settings.entities.drawer.name")}
          required
          error={errors.name ?? null}
          width="full"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              readOnly={readOnly}
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                refusals.edited("name");
              }}
              className={controlClass(errors.name !== undefined)}
            />
          )}
        </Field>
        <Field
          name="country_code"
          label={t("settings.entities.drawer.country")}
          optional
          error={errors.country_code ?? null}
          width="text"
        >
          {(control) => (
            <Combobox
              control={control}
              options={countries}
              value={country}
              invalid={errors.country_code !== undefined}
              onChange={(next) => {
                if (!readOnly) {
                  setCountry(next);
                  refusals.edited("country_code");
                }
              }}
            />
          )}
        </Field>
        <Field
          name="functional_currency"
          label={t("settings.entities.drawer.functionalCurrency")}
          required
          error={errors.functional_currency ?? null}
          help={entity === null ? undefined : t("settings.entities.drawer.fixedAfterPostingHelp")}
          width="text"
        >
          {(control) => (
            <Select<string>
              control={control}
              options={currencyCodes.map((value) => ({ value, label: value }))}
              value={currency}
              invalid={errors.functional_currency !== undefined}
              onChange={(next) => {
                if (!readOnly) {
                  setCurrency(next);
                  refusals.edited("functional_currency");
                }
              }}
            />
          )}
        </Field>
        <Field
          name="time_zone"
          label={t("settings.entities.drawer.timeZone")}
          required
          error={errors.time_zone ?? null}
          width="text"
        >
          {(control) => (
            <Combobox
              control={control}
              options={zones}
              value={timeZone}
              invalid={errors.time_zone !== undefined}
              onChange={(next) => {
                if (!readOnly) {
                  setTimeZone(next);
                  refusals.edited("time_zone");
                }
              }}
            />
          )}
        </Field>
        <Field
          name="calendar_id"
          label={t("settings.entities.drawer.calendar")}
          required
          error={errors.calendar_id ?? null}
          width="text"
        >
          {(control) => (
            <Select<string>
              control={control}
              options={calendars.map((calendar) => ({
                value: calendar.id,
                label: `${calendar.code} · ${calendar.name}`,
              }))}
              value={calendarId}
              invalid={errors.calendar_id !== undefined}
              onChange={(next) => {
                if (!readOnly && entity === null) {
                  setCalendarId(next);
                  refusals.edited("calendar_id");
                }
              }}
            />
          )}
        </Field>
        <Field
          name="parent_entity_id"
          label={t("settings.entities.drawer.parent")}
          optional
          error={errors.parent_entity_id ?? null}
          width="text"
        >
          {(control) => (
            <Combobox
              control={control}
              options={parents.map((candidate) => ({
                value: candidate.id,
                label: `${candidate.code} · ${candidate.name}`,
              }))}
              value={parentId}
              invalid={errors.parent_entity_id !== undefined}
              onChange={(next) => {
                if (!readOnly) {
                  setParentId(next);
                  refusals.edited("parent_entity_id");
                }
              }}
            />
          )}
        </Field>
        <Field
          name="tax_id"
          label={t("settings.entities.drawer.taxId")}
          optional
          error={errors.tax_id ?? null}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              readOnly={readOnly}
              value={taxId}
              onChange={(event) => {
                setTaxId(event.target.value);
                refusals.edited("tax_id");
              }}
              className={controlClass(errors.tax_id !== undefined)}
            />
          )}
        </Field>
        <fieldset className="flex flex-col gap-2">
          <legend className="text-body-sm font-medium text-fg-1">
            {t("settings.entities.drawer.books")}
          </legend>
          {entity === null ? (
            <p className="text-body-sm text-fg-3">
              {t("settings.entities.drawer.booksAfterCreate")}
            </p>
          ) : null}
          {BOOK_CODES.map((bookCode) => (
            <BookRow
              key={bookCode}
              code={bookCode}
              label={bookLabel(bookCode, books)}
              draft={drafts[bookCode]}
              readOnly={readOnly || (entity === null && bookCode !== "ASC606")}
              lockEnabled={entity === null && bookCode === "ASC606"}
              error={errors[`books.${bookCode}`] ?? null}
              onChange={(next) => {
                setDrafts((previous) => ({ ...previous, [bookCode]: next }));
                refusals.edited(`books.${bookCode}`);
              }}
            />
          ))}
        </fieldset>
        <label htmlFor={activeId} className="flex items-center gap-2 text-body-sm text-fg-1">
          <input
            id={activeId}
            type="checkbox"
            checked={active}
            disabled={readOnly}
            onChange={(event) => setActive(event.target.checked)}
            className="size-4"
          />
          {t("settings.entities.drawer.active")}
        </label>
      </form>
    </Drawer>
  );
}

function bookChanged(entity: Entity, code: BookCode, draft: BookDraft): boolean {
  const row = entityBook(entity, code);
  const wasEnabled = row?.is_enabled ?? false;
  const wasKey = row?.first_period_key ?? "";
  return draft.enabled !== wasEnabled || (draft.enabled && draft.firstPeriodKey.trim() !== wasKey);
}

function BookRow({
  code,
  label,
  draft,
  readOnly,
  lockEnabled,
  error,
  onChange,
}: {
  readonly code: BookCode;
  readonly label: string;
  readonly draft: BookDraft;
  readonly readOnly: boolean;
  /** The primary book of a new entity is always enabled (`EntityIn.first_period_key`). */
  readonly lockEnabled: boolean;
  readonly error: string | null;
  readonly onChange: (next: BookDraft) => void;
}) {
  const checkboxId = useId();
  return (
    <div className="flex flex-wrap items-end gap-3" data-testid={`SF-15-book-${code}`}>
      <label
        htmlFor={checkboxId}
        className="flex h-[var(--control-h)] items-center gap-2 text-body-sm text-fg-1"
      >
        <input
          id={checkboxId}
          type="checkbox"
          checked={draft.enabled}
          disabled={readOnly || lockEnabled}
          onChange={(event) => onChange({ ...draft, enabled: event.target.checked })}
          className="size-4"
        />
        {label}
      </label>
      {draft.enabled ? (
        <Field
          name={`first_period_${code}`}
          label={t("settings.entities.drawer.firstPeriod", { book: label })}
          required
          error={error}
          help={t("settings.entities.drawer.firstPeriodHelp")}
          width="period"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              readOnly={readOnly}
              value={draft.firstPeriodKey}
              onChange={(event) => onChange({ ...draft, firstPeriodKey: event.target.value })}
              className={`${controlClass(error !== null)} font-mono`}
            />
          )}
        </Field>
      ) : null}
    </div>
  );
}
