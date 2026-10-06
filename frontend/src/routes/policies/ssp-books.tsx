// SF-13:ssp-books SSP books (SCREENS §11.0 frame, §11.4 books grid, "New SSP book" drawer and states;
// §0.4 RT-65 and the RT-66 redirect; §0.7 SCR-PERM-01, SCR-PERM-02; DESIGN_SYSTEM DS-CMP-09, DS-CMP-10,
// DS-CMP-23; 04 API-R-26 `GET, POST /ssp-books`, `GET, POST /ssp-books/{id}/versions`; BUILD_SPEC
// RFD-24). The `h1` "Policies" with the route tabs, the DataGrid "SSP books" and, for `ssp.create`, the
// "New SSP book" drawer. A book code opens `/policies/ssp-books/:bookId`, which redirects to the current
// approved version, else the draft, else the newest version (L4-5-Q-51). The import overflow items
// target import screens that are not built (XR-14; L4-5-Q-52).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useId, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import type { GridColumn, GridSource } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useNoAnswer, useToast } from "../../components/feedback/Toast";
import { DateInput } from "../../components/form/DateInput";
import { controlClass, Field } from "../../components/form/Field";
import { Select } from "../../components/form/Select";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { Modal } from "../../components/ui/Modal";
import { useAccess } from "../../lib/access";
import { type CommandKeys, useCommandKeys } from "../../lib/api/commands";
import { ApiProblem, readProblem } from "../../lib/api/problems";
import { useMe } from "../../lib/api/queries/me";
import { fetchTenantCurrencies, tenantCurrenciesKey } from "../../lib/api/queries/ssp-calculator";
import {
  EVERY_SSP_BOOK,
  EVERY_SSP_BOOK_VERSION,
  fetchSspBook,
  fetchSspBooksPage,
  fetchSspBookVersion,
  fetchSspBookVersions,
  landingVersionId,
  RESOLUTION_MODES,
  type ResolutionMode,
  resolutionLabel,
  scopeText,
  SSP_BOOKS_PATH,
  SSP_CREATE_PERMISSION,
  SSP_READ_PERMISSION,
  type SspBook,
  sspBookKey,
  sspBooksKey,
  type SspBookVersion,
  sspBookVersionKey,
  sspBookVersionRoute,
  sspBookVersionsKey,
  sspBookRoute,
  versionText,
} from "../../lib/api/queries/ssp-books";
import { entitiesKey, fetchActiveEntities } from "../../lib/api/queries/tenant";
import { fieldMessages, useFieldRefusals } from "../../lib/api/refusals";
import { t } from "../../lib/i18n/t";
import { PoliciesPageHeader } from "./revenue";

export interface SspPageProps {
  /** The page body for an `ssp.read` holder; `create` holds `ssp.create` (SCR-PERM-02). */
  readonly children: (create: boolean) => ReactNode;
}

/** SCREENS §11.0 list page frame for the SSP pages, with the SCR-PERM-01 access-limited state. */
export function SspPage({ children }: SspPageProps) {
  const me = useMe();
  const access = useAccess();
  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={t("policies.title")} shape="rows" count={8} />;
  } else if (!access.holdsAnywhere(SSP_READ_PERMISSION)) {
    body = <SspAccessLimited />;
  } else {
    body = children(access.holdsAnywhere(SSP_CREATE_PERMISSION));
  }
  return (
    <div className="flex w-full flex-col gap-6">
      <PoliciesPageHeader />
      {body}
    </div>
  );
}

/** SCR-PERM-01 for `ssp.read`. */
export function SspAccessLimited() {
  return (
    <EmptyState
      title={t("settings.access.title", { area: t("policies.title") })}
      description={t("settings.access.description", {
        permission: t("settings.access.permission.sspRead"),
      })}
    />
  );
}

/** SCREENS §0.7 SCR-ST-05 message: the problem title, then "Reference <request id>." (CPY-05). */
export function problemText(error: unknown): string {
  if (error instanceof ApiProblem) {
    return error.requestId === null
      ? error.title
      : `${error.title} ${t("approvals.reference", { reference: error.requestId })}`;
  }
  return error instanceof Error ? error.message : String(error);
}

function DraftLink({ book }: { readonly book: SspBook }) {
  const draftId = book.draft_version_id ?? "";
  const draft = useQuery({
    queryKey: sspBookVersionKey(draftId),
    queryFn: () => fetchSspBookVersion(draftId),
    enabled: book.draft_version_id !== null,
  });
  if (book.draft_version_id === null) {
    return "—";
  }
  const label =
    draft.data === undefined
      ? t("policies.sspBooks.draftPending")
      : t("policies.sspBooks.draftLink", { version: draft.data.version_no });
  return (
    <Link
      to={sspBookVersionRoute(book.id, book.draft_version_id)}
      className="text-accent-fg hover:underline"
    >
      {label}
    </Link>
  );
}

/** SCREENS §11.4 books grid columns. */
export function bookColumns(): readonly GridColumn<SspBook>[] {
  return [
    {
      id: "code",
      header: t("policies.sspBooks.column.book"),
      kind: "identifier",
      value: (book) => book.code,
      href: (book) => sspBookRoute(book.id),
      sortKey: "code",
      width: 144,
    },
    {
      id: "name",
      header: t("policies.sspBooks.column.name"),
      kind: "text",
      value: (book) => book.name,
      sortKey: "name",
      width: 208,
    },
    {
      id: "scope",
      header: t("policies.sspBooks.column.scope"),
      kind: "text",
      value: (book) => scopeText(book),
      width: 192,
    },
    {
      id: "resolution",
      header: t("policies.sspBooks.column.resolution"),
      kind: "text",
      value: (book) => resolutionLabel(book.resolution_mode),
      width: 176,
    },
    {
      id: "current",
      header: t("policies.sspBooks.column.currentVersion"),
      kind: "text",
      value: (book) => (book.current_version === null ? null : versionText(book.current_version)),
      width: 176,
    },
    {
      id: "effectiveFrom",
      header: t("policies.sspBooks.column.effectiveFrom"),
      kind: "date",
      value: (book) => book.current_version?.effective_from_date ?? null,
      width: 144,
    },
    {
      id: "effectiveTo",
      header: t("policies.sspBooks.column.effectiveTo"),
      kind: "date",
      value: (book) => book.current_version?.effective_to_date ?? null,
      width: 128,
    },
    {
      id: "draft",
      header: t("policies.sspBooks.column.draft"),
      kind: "text",
      value: (book) => book.draft_version_id,
      render: (book) => <DraftLink book={book} />,
      width: 120,
    },
  ];
}

const BOOKS_SOURCE: GridSource<SspBook> = {
  queryKey: sspBooksKey(),
  fetchPage: fetchSspBooksPage,
};

export function SspBooks() {
  return <SspPage>{(create) => <BooksGrid create={create} />}</SspPage>;
}

function BooksGrid({ create }: { readonly create: boolean }) {
  const [creating, setCreating] = useState(false);
  return (
    <>
      <div className="flex h-120 min-h-0 flex-col">
        <DataGrid<SspBook>
          name="ssp-books"
          title={t("policies.sspBooks.title")}
          countLabel={(count, formatted) => t("policies.sspBooks.count", { count, formatted })}
          columns={bookColumns()}
          source={BOOKS_SOURCE}
          rowKey={(book) => book.id}
          rowLabel={(book) => book.code}
          testIdPrefix="SF-13"
          rowTestKey={(book) => book.code}
          toolbarActions={
            create ? (
              <Button variant="primary" size="sm" onClick={() => setCreating(true)}>
                {t("policies.sspBooks.new")}
              </Button>
            ) : undefined
          }
          emptyState={
            <EmptyState
              title={t("policies.sspBooks.empty.title")}
              description={t("policies.sspBooks.empty.description")}
              action={
                create
                  ? {
                      label: t("policies.sspBooks.empty.action"),
                      onAction: () => setCreating(true),
                    }
                  : undefined
              }
            />
          }
        />
      </div>
      {creating ? <NewSspBookDrawer onClose={() => setCreating(false)} /> : null}
    </>
  );
}

type Created<T> =
  { readonly ok: true; readonly data: T } | { readonly ok: false; readonly problem: ApiProblem };

/** One command under the key `keys` holds for it (DG-FE-05 rev 1.156); a network failure rejects. */
export async function postCommand<T>(
  keys: CommandKeys,
  path: string,
  body: unknown,
): Promise<Created<T>> {
  const response = await keys.send("POST", path, { body });
  if (!response.ok) {
    return { ok: false, problem: await readProblem(response) };
  }
  return { ok: true, data: (await response.json()) as T };
}

const ALL_ENTITIES = "*";
const ANY_CURRENCY = "*";

/** The API members the fields of "New SSP book" send (DG-FE-06 rev 1.228). */
const BOOK_MEMBERS = {
  code: ["code"],
  name: ["name"],
  description: ["description"],
  entity_code: ["entity_code"],
  currency: ["currency"],
  channel: ["channel"],
  segment: ["segment"],
  resolution_mode: ["resolution_mode"],
} as const;

/**
 * SCREENS §11.4 "New SSP book": Code, Name, Description, Entity, Currency, Channel, Segment, Resolution
 * mode; "Create SSP book" posts `POST /ssp-books`.
 */
export function NewSspBookDrawer({ onClose }: { readonly onClose: () => void }) {
  const toast = useToast();
  const noAnswer = useNoAnswer();
  const keys = useCommandKeys();
  const queryClient = useQueryClient();
  const formId = useId();
  const entities = useQuery({ queryKey: entitiesKey(), queryFn: fetchActiveEntities });
  const currencies = useQuery({ queryKey: tenantCurrenciesKey(), queryFn: fetchTenantCurrencies });
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [entity, setEntity] = useState<string>(ALL_ENTITIES);
  const [currency, setCurrency] = useState<string>(ANY_CURRENCY);
  const [channel, setChannel] = useState("");
  const [segment, setSegment] = useState("");
  const [mode, setMode] = useState<ResolutionMode>("EFFECTIVE_DATE");
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [local, setLocal] = useState<Readonly<Record<string, string>>>({});
  const refusals = useFieldRefusals(problem, BOOK_MEMBERS);
  const errors: Partial<Record<string, string>> = { ...fieldMessages(refusals.fields), ...local };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending) {
      return;
    }
    const found: Record<string, string> = {};
    if (code.trim() === "") {
      found.code = t("policies.sspBooks.drawer.codeRequired");
    }
    if (name.trim() === "") {
      found.name = t("policies.sspBooks.drawer.nameRequired");
    }
    setLocal(found);
    if (Object.keys(found).length > 0) {
      return;
    }
    setPending(true);
    setProblem(null);
    const created = await postCommand<SspBook>(keys, SSP_BOOKS_PATH, {
      code: code.trim(),
      name: name.trim(),
      resolution_mode: mode,
      ...(description.trim() === "" ? {} : { description: description.trim() }),
      ...(entity === ALL_ENTITIES ? {} : { entity_code: entity }),
      ...(currency === ANY_CURRENCY ? {} : { currency }),
      ...(channel.trim() === "" ? {} : { channel: channel.trim() }),
      ...(segment.trim() === "" ? {} : { segment: segment.trim() }),
    }).catch(() => null);
    setPending(false);
    if (created === null) {
      // No answer: the drawer keeps its input, and the next press sends the same key (DG-FE-05).
      noAnswer();
      return;
    }
    if (!created.ok) {
      setProblem(created.problem);
      return;
    }
    await queryClient.invalidateQueries({ queryKey: EVERY_SSP_BOOK });
    toast.show({
      tone: "positive",
      message: t("policies.sspBooks.drawer.created", { code: created.data.code }),
    });
    onClose();
  };

  const text = (
    field: "code" | "name" | "channel" | "segment",
    label: string,
    value: string,
    onChange: (next: string) => void,
    options: { readonly required?: boolean; readonly mono?: boolean } = {},
  ) => (
    <Field
      name={`ssp_book_${field}`}
      label={label}
      required={options.required === true}
      optional={options.required !== true}
      error={errors[field] ?? null}
      width="text"
    >
      {(control) => (
        <input
          {...control}
          type="text"
          value={value}
          onChange={(event) => {
            onChange(event.target.value);
            refusals.edited(field);
          }}
          className={`${controlClass(errors[field] !== undefined)}${options.mono === true ? " font-mono" : ""}`}
        />
      )}
    </Field>
  );

  return (
    <Drawer
      open
      title={t("policies.sspBooks.new")}
      dirty={code !== "" || name !== "" || description !== ""}
      submitting={pending}
      banner={
        refusals.banner === null ? undefined : (
          <RefusalBanner problem={refusals.banner} placed={refusals.placed} />
        )
      }
      primaryAction={{ label: t("policies.sspBooks.drawer.create"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        onSubmit={(event) => void submit(event)}
        className="flex flex-col gap-4"
      >
        {text("code", t("policies.sspBooks.drawer.code"), code, setCode, {
          required: true,
          mono: true,
        })}
        {text("name", t("policies.sspBooks.drawer.name"), name, setName, { required: true })}
        <Field
          name="ssp_book_description"
          label={t("policies.sspBooks.drawer.description")}
          optional
          error={errors.description ?? null}
          width="text"
        >
          {(control) => (
            <textarea
              {...control}
              rows={3}
              value={description}
              onChange={(event) => {
                setDescription(event.target.value);
                refusals.edited("description");
              }}
              className={controlClass(errors.description !== undefined, true)}
            />
          )}
        </Field>
        <Field
          name="ssp_book_entity"
          label={t("policies.sspBooks.drawer.entity")}
          optional
          error={errors.entity_code ?? null}
          width="text"
        >
          {(control) => (
            <Select<string>
              control={control}
              options={[
                { value: ALL_ENTITIES, label: t("policies.sspBooks.allEntities") },
                ...(entities.data ?? []).map((item) => ({
                  value: item.code,
                  label: `${item.code} · ${item.name}`,
                })),
              ]}
              value={entity}
              onChange={(next) => {
                setEntity(next);
                refusals.edited("entity_code");
              }}
            />
          )}
        </Field>
        <Field
          name="ssp_book_currency"
          label={t("policies.sspBooks.drawer.currency")}
          optional
          error={errors.currency ?? null}
          width="text"
        >
          {(control) => (
            <Select<string>
              control={control}
              options={[
                { value: ANY_CURRENCY, label: t("policies.sspBooks.anyCurrency") },
                ...(currencies.data ?? []).map((item) => ({
                  value: item.currency_code,
                  label: item.currency_code,
                })),
              ]}
              value={currency}
              onChange={(next) => {
                setCurrency(next);
                refusals.edited("currency");
              }}
            />
          )}
        </Field>
        {text("channel", t("policies.sspBooks.drawer.channel"), channel, setChannel)}
        {text("segment", t("policies.sspBooks.drawer.segment"), segment, setSegment)}
        <Field
          name="ssp_book_resolution"
          label={t("policies.sspBooks.drawer.resolution")}
          required
          help={t("policies.sspBooks.drawer.resolutionHelp")}
          error={errors.resolution_mode ?? null}
          width="text"
        >
          {(control) => (
            <Select<ResolutionMode>
              control={control}
              options={RESOLUTION_MODES.map((value) => ({ value, label: resolutionLabel(value) }))}
              value={mode}
              onChange={(next) => {
                setMode(next);
                refusals.edited("resolution_mode");
              }}
            />
          )}
        </Field>
      </form>
    </Drawer>
  );
}

/** The API members the fields of "New draft version" send; the version copied has no field. */
const DRAFT_MEMBERS = {
  legacy_version_label: ["legacy_version_label"],
  effective_from_date: ["effective_from_date"],
  methodology_label: ["methodology_label"],
} as const;

export interface NewDraftModalProps {
  readonly book: SspBook;
  /** The version whose entries the draft copies; null starts an empty draft. */
  readonly source: SspBookVersion | null;
  readonly onClose: () => void;
}

/**
 * The first draft of a book without versions (L4-5-Q-51): Version label, Effective from and
 * Methodology label; "Create draft version" posts `POST /ssp-books/{id}/versions` and opens the draft.
 */
export function NewDraftModal({ book, source, onClose }: NewDraftModalProps) {
  const toast = useToast();
  const noAnswer = useNoAnswer();
  const keys = useCommandKeys();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const formId = useId();
  const [label, setLabel] = useState("");
  const [typed, setTyped] = useState("");
  const [date, setDate] = useState<string | null>(null);
  const [formatError, setFormatError] = useState<string | null>(null);
  const [methodology, setMethodology] = useState(source?.methodology_label ?? "");
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [local, setLocal] = useState<Readonly<Record<string, string>>>({});
  const refusals = useFieldRefusals(problem, DRAFT_MEMBERS);
  const errors: Partial<Record<string, string>> = { ...fieldMessages(refusals.fields), ...local };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending || formatError !== null) {
      return;
    }
    const found: Record<string, string> = {};
    if (methodology.trim() === "") {
      found.methodology_label = t("policies.sspVersion.meta.methodologyRequired");
    }
    setLocal(found);
    if (Object.keys(found).length > 0) {
      return;
    }
    setPending(true);
    setProblem(null);
    const created = await postCommand<SspBookVersion>(
      keys,
      `${SSP_BOOKS_PATH}/${book.id}/versions`,
      {
        methodology_label: methodology.trim(),
        ...(source === null ? {} : { copy_from_version_id: source.id }),
        ...(label.trim() === "" ? {} : { legacy_version_label: label.trim() }),
        ...(date === null ? {} : { effective_from_date: date }),
      },
    ).catch(() => null);
    setPending(false);
    if (created === null) {
      noAnswer();
      return;
    }
    if (!created.ok) {
      setProblem(created.problem);
      return;
    }
    await queryClient.invalidateQueries({ queryKey: EVERY_SSP_BOOK });
    await queryClient.invalidateQueries({ queryKey: EVERY_SSP_BOOK_VERSION });
    toast.show({
      tone: "positive",
      message: t("policies.sspVersion.draftCreated", {
        code: book.code,
        version: created.data.version_no,
      }),
    });
    onClose();
    void navigate(sspBookVersionRoute(book.id, created.data.id));
  };

  return (
    <Modal
      open
      variant="form"
      title={t("policies.sspVersion.newDraft")}
      primaryAction={{ label: t("policies.sspVersion.createDraft"), form: formId }}
      submitting={pending}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        onSubmit={(event) => void submit(event)}
        className="flex flex-col gap-4"
      >
        <RefusalBanner problem={refusals.banner} placed={refusals.placed} headingLevel={3} />
        <Field
          name="draft_version_label"
          label={t("policies.sspVersion.meta.label")}
          optional
          error={errors.legacy_version_label ?? null}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              value={label}
              onChange={(event) => {
                setLabel(event.target.value);
                refusals.edited("legacy_version_label");
              }}
              className={controlClass(errors.legacy_version_label !== undefined)}
            />
          )}
        </Field>
        <Field
          name="draft_effective_from"
          label={t("policies.sspVersion.meta.effectiveFrom")}
          optional
          error={formatError ?? errors.effective_from_date ?? null}
          width="date"
        >
          {(control) => (
            <DateInput
              control={control}
              value={typed}
              onChange={(next) => {
                setTyped(next);
                refusals.edited("effective_from_date");
              }}
              onValue={setDate}
              onFormatError={setFormatError}
              invalid={formatError !== null}
            />
          )}
        </Field>
        <Field
          name="draft_methodology"
          label={t("policies.sspVersion.meta.methodology")}
          required
          error={errors.methodology_label ?? null}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              value={methodology}
              onChange={(event) => {
                setMethodology(event.target.value);
                refusals.edited("methodology_label");
              }}
              className={controlClass(errors.methodology_label !== undefined)}
            />
          )}
        </Field>
      </form>
    </Modal>
  );
}

/** RT-66 note: `/policies/ssp-books/:bookId` opens the book's landing version (L4-5-Q-51). */
export function SspBookRedirect() {
  const { bookId = "" } = useParams();
  const me = useMe();
  const access = useAccess();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const read = access.holdsAnywhere(SSP_READ_PERMISSION);
  const book = useQuery({
    queryKey: sspBookKey(bookId),
    queryFn: () => fetchSspBook(bookId),
    enabled: read,
  });
  const needsVersions =
    book.data !== undefined &&
    book.data.current_version === null &&
    book.data.draft_version_id === null;
  const versions = useQuery({
    queryKey: sspBookVersionsKey(bookId),
    queryFn: () => fetchSspBookVersions(bookId),
    enabled: read && needsVersions,
  });
  const region = t("policies.sspVersion.region");

  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={region} shape="rows" count={8} />;
  } else if (!read) {
    body = <SspAccessLimited />;
  } else if (book.error !== null || versions.error !== null) {
    const failure = book.error ?? versions.error;
    body =
      failure instanceof ApiProblem && failure.status === 404 ? (
        <EmptyState
          title={t("policies.sspBooks.notFound.title")}
          description={t("policies.version.notFound.description")}
          action={{
            label: t("policies.sspBooks.notFound.action"),
            onAction: () => void navigate("/policies/ssp-books"),
          }}
        />
      ) : (
        <Banner tone="negative" title={t("policies.sspVersion.loadError")} headingLevel={2}>
          {problemText(failure)}
        </Banner>
      );
  } else if (book.data === undefined || (needsVersions && versions.data === undefined)) {
    body = <Skeleton region={region} shape="rows" count={8} />;
  } else {
    const target = landingVersionId(book.data, versions.data ?? []);
    if (target !== null) {
      return <Navigate to={sspBookVersionRoute(bookId, target)} replace />;
    }
    const create = access.holdsAnywhere(SSP_CREATE_PERMISSION);
    body = (
      <>
        <EmptyState
          title={t("policies.sspBooks.noVersions.title", { code: book.data.code })}
          description={t("policies.sspBooks.noVersions.description")}
          action={
            create
              ? { label: t("policies.sspVersion.newDraft"), onAction: () => setCreating(true) }
              : undefined
          }
        />
        {creating ? (
          <NewDraftModal book={book.data} source={null} onClose={() => setCreating(false)} />
        ) : null}
      </>
    );
  }
  return (
    <div className="flex w-full flex-col gap-6">
      <PoliciesPageHeader />
      {body}
    </div>
  );
}
