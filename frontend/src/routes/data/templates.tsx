// SF-10:templates Templates and mapping profiles (SCREENS §12.4; §0.3 SCR-IA-02; §0.4 RT-45; §11.0 header
// commands; §0.7 SCR-PERM-01, SCR-PERM-02, SCR-ST-05; §0.8 E-12; DESIGN_SYSTEM DS-CMP-09, DS-CMP-10,
// DS-CMP-13, DS-CMP-19, DS-CMP-21, DS-CMP-23; 04 API-R-43 `GET /import-templates`,
// `GET /import-templates/{code}/download`, `GET, POST /import-mapping-profiles`,
// `POST /import-mapping-profiles/{id}/test`, `/submit`; BUILD_SPEC DIN-15, DIN-10). The Data frame and
// the `h1` "Import templates"; the Family chip (`?f.family=is:LEGACY_V1`) over the static table "Import
// templates" with one "Download <name>" button per template; then the DataGrid "Mapping profiles" with,
// for `config.author`, "New mapping profile" (drawer) and the version commands "Run tests" and "Submit
// for approval". The mapping profile routes are DIN-10's, built in the same level (integration after
// merge, D-81).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useId, useMemo, useState } from "react";
import { useLocation } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import {
  type GridColumn,
  type GridColumnState,
  type GridSource,
  initialColumnState,
} from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useNoAnswer, useToast } from "../../components/feedback/Toast";
import { FilterBar } from "../../components/filter-bar/FilterBar";
import { type FilterField, parseFilters } from "../../components/filter-bar/filters";
import { controlClass, Field } from "../../components/form/Field";
import { Select } from "../../components/form/Select";
import { DotsThree, DownloadSimple, Plus, Trash } from "../../components/icons/registry";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { Menu, type MenuItem } from "../../components/ui/Menu";
import { Modal } from "../../components/ui/Modal";
import { chipFor, OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import { type Access, useAccess } from "../../lib/access";
import { useCommandKeys } from "../../lib/api/commands";
import { ApiProblem } from "../../lib/api/problems";
import {
  downloadTemplate,
  familyLabel,
  fetchImportTemplates,
  type ImportTemplate,
  importTemplatesKey,
  parameterLabels,
  TEMPLATE_FAMILIES,
  templateName,
} from "../../lib/api/queries/import-templates";
import { IMPORT_READ_PERMISSION } from "../../lib/api/queries/imports";
import {
  CONFIG_AUTHOR_PERMISSION,
  createMappingProfile,
  EVERY_MAPPING_PROFILE,
  fetchMappingProfilesPage,
  type MappingProfile,
  mappingProfilesKey,
  type ProfileOutcome,
  profileActions,
  submitMappingProfile,
  testMappingProfile,
} from "../../lib/api/queries/mapping-profiles";
import { useMe } from "../../lib/api/queries/me";
import { useFieldRefusals } from "../../lib/api/refusals";
import { formatList, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { DataAccessLimited, DataPageHeader } from "./imports";

/** SCREENS §0.7 SCR-ST-05 message: the problem title, then "Reference <request id>." (CPY-05). */
function problemText(problem: unknown): string {
  if (problem instanceof ApiProblem) {
    return problem.requestId === null
      ? problem.title
      : `${problem.title} ${t("approvals.reference", { reference: problem.requestId })}`;
  }
  return problem instanceof Error ? problem.message : String(problem);
}

export function ImportTemplates() {
  const me = useMe();
  const access = useAccess();
  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={t("data.templates.title")} shape="rows" count={10} />;
  } else if (!access.holdsAnywhere(IMPORT_READ_PERMISSION)) {
    body = <DataAccessLimited area={t("data.access.templates")} />;
  } else {
    body = (
      <>
        <TemplatesTable />
        <MappingProfilesPanel access={access} />
      </>
    );
  }
  return (
    <div data-testid="SF-10-templates-page" className="flex flex-col gap-6">
      <DataPageHeader title={t("data.templates.title")} />
      {body}
    </div>
  );
}

function familyFields(): readonly FilterField[] {
  return [
    {
      name: "family",
      label: t("data.templates.filter.family"),
      kind: "enum",
      operators: ["is"],
      options: TEMPLATE_FAMILIES.map((family) => ({ value: family, label: familyLabel(family) })),
    },
  ];
}

const HEAD_CELL = "py-2 pe-4 text-start font-medium";
const BODY_CELL = "py-2 pe-4";

/** SCREENS §12.4 templates static table with the Family chip and the per-template download. */
function TemplatesTable() {
  const location = useLocation();
  const toast = useToast();
  const headingId = useId();
  const fields = useMemo(() => familyFields(), []);
  const family =
    parseFilters(location.search, fields).filters.find((filter) => filter.field === "family")
      ?.values[0] ?? null;
  const templates = useQuery({ queryKey: importTemplatesKey(), queryFn: fetchImportTemplates });
  const download = (template: ImportTemplate) => {
    void downloadTemplate(template).catch(() => {
      toast.show({
        tone: "negative",
        message: t("data.templates.downloadFailed", { name: templateName(template) }),
      });
    });
  };

  let body: ReactNode;
  if (templates.isError) {
    body = (
      <Banner
        tone="negative"
        title={t("data.templates.loadError")}
        actions={
          <Button variant="secondary" size="sm" onClick={() => void templates.refetch()}>
            {t("data.templates.retry")}
          </Button>
        }
      >
        {problemText(templates.error)}
      </Banner>
    );
  } else if (templates.data === undefined) {
    body = <Skeleton region={t("data.templates.caption")} shape="rows" count={8} />;
  } else {
    const shown = templates.data.filter(
      (template) => family === null || template.family === family,
    );
    body = (
      <table data-testid="SF-10-grid-templates" className="w-full border-collapse text-body-sm">
        <caption className="sr-only">{t("data.templates.caption")}</caption>
        <thead>
          <tr className="border-b border-default text-fg-2">
            <th scope="col" className={HEAD_CELL}>
              {t("data.templates.column.template")}
            </th>
            <th scope="col" className={HEAD_CELL}>
              {t("data.templates.column.code")}
            </th>
            <th scope="col" className={HEAD_CELL}>
              {t("data.templates.column.family")}
            </th>
            <th scope="col" className={HEAD_CELL}>
              {t("data.templates.column.format")}
            </th>
            <th scope="col" className={`${HEAD_CELL} text-end`}>
              {t("data.templates.column.version")}
            </th>
            <th scope="col" className={HEAD_CELL}>
              {t("data.templates.column.parameters")}
            </th>
            <th scope="col" className="py-2 text-end font-medium">
              {t("data.templates.column.download")}
            </th>
          </tr>
        </thead>
        <tbody>
          {shown.map((template) => {
            const parameters = parameterLabels(template);
            const name = templateName(template);
            return (
              <tr key={template.code} className="border-b border-hairline align-middle">
                <th scope="row" className={`${BODY_CELL} text-start font-normal text-fg-1`}>
                  {name}
                </th>
                <td className={`${BODY_CELL} font-mono text-mono text-fg-2`}>{template.code}</td>
                <td className={BODY_CELL}>
                  <OutlineChip label={familyLabel(template.family)} />
                </td>
                <td className={`${BODY_CELL} text-fg-2`}>{template.file_format}</td>
                <td className={`${BODY_CELL} num text-end text-fg-1`}>{template.version}</td>
                <td className={`${BODY_CELL} text-fg-2`}>
                  {parameters.length === 0 ? NO_VALUE : formatList(parameters, "and")}
                </td>
                <td className="py-1.5 text-end">
                  <Button
                    variant="secondary"
                    size="sm"
                    icon={DownloadSimple}
                    aria-label={t("data.templates.downloadName", { name })}
                    onClick={() => download(template)}
                  >
                    {t("data.templates.download")}
                  </Button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  }
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3">
      <h2 id={headingId} className="text-title-md text-fg-1">
        {t("data.templates.section")}
      </h2>
      <FilterBar fields={fields} testId="SF-10-filter-templates" />
      {body}
    </section>
  );
}

/** SCREENS §12.4 mapping profiles grid columns, with the version commands for `config.author`. */
function profileColumns(
  templateNames: ReadonlyMap<string, string>,
  actions: ((profile: MappingProfile) => readonly MenuItem[]) | undefined,
): readonly GridColumn<MappingProfile>[] {
  const columns: GridColumn<MappingProfile>[] = [
    {
      id: "code",
      header: t("data.mappingProfiles.column.profile"),
      kind: "identifier",
      value: (profile) => profile.code,
      sortKey: "code",
      width: 176,
    },
    {
      id: "name",
      header: t("data.mappingProfiles.column.name"),
      kind: "text",
      value: (profile) => profile.name,
      width: 240,
    },
    {
      id: "template",
      header: t("data.mappingProfiles.column.template"),
      kind: "text",
      value: (profile) => templateNames.get(profile.template_code) ?? profile.template_code,
      width: 224,
    },
    {
      id: "version",
      header: t("data.mappingProfiles.column.version"),
      kind: "number",
      numberKind: "count",
      value: (profile) => String(profile.version_no),
      sortKey: "version_no",
      width: 96,
    },
    {
      id: "status",
      header: t("data.mappingProfiles.column.status"),
      kind: "status",
      value: (profile) => profile.status,
      render: (profile) => {
        const chip = chipFor("E-12", profile.status);
        return chip === null ? null : <StatusChip status={chip.status} />;
      },
      width: 160,
    },
    {
      id: "effective_from",
      header: t("data.mappingProfiles.column.effectiveFrom"),
      kind: "timestamp",
      value: (profile) => profile.effective_from,
    },
  ];
  if (actions !== undefined) {
    columns.push({
      id: "actions",
      header: t("data.mappingProfiles.column.actions"),
      kind: "actions",
      value: () => null,
      render: (profile) => {
        const items = actions(profile);
        return items.length === 0 ? null : (
          <Menu
            label={t("data.mappingProfiles.row.menu", { code: profile.code })}
            icon={DotsThree}
            iconOnly
            variant="ghost"
            size="sm"
            align="end"
            items={items}
          />
        );
      },
    });
  }
  return columns;
}

function MappingProfilesPanel({ access }: { readonly access: Access }) {
  const headingId = useId();
  const queryClient = useQueryClient();
  const toast = useToast();
  const noAnswer = useNoAnswer();
  const keys = useCommandKeys();
  const author = access.holdsAnywhere(CONFIG_AUTHOR_PERMISSION);
  const templates = useQuery({ queryKey: importTemplatesKey(), queryFn: fetchImportTemplates });
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState<MappingProfile | null>(null);

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: EVERY_MAPPING_PROFILE });
  };
  const report = (outcome: ProfileOutcome, message: (profile: MappingProfile) => string) => {
    toast.show(
      outcome.ok
        ? { tone: "positive", message: message(outcome.profile) }
        : { tone: "negative", message: problemText(outcome.problem) },
    );
  };
  const runTests = async (profile: MappingProfile) => {
    try {
      report(await testMappingProfile(keys, profile.id), (tested) =>
        t("data.mappingProfiles.tested", { code: tested.code, version: tested.version_no }),
      );
    } catch {
      // No answer: the next press sends the test under the same key (DG-FE-05).
      noAnswer();
    }
    await refresh();
  };
  const templateNames = useMemo(
    () =>
      new Map((templates.data ?? []).map((template) => [template.code, templateName(template)])),
    [templates.data],
  );
  const columns = useMemo(
    () =>
      profileColumns(
        templateNames,
        author
          ? (profile) =>
              profileActions(profile.status).map((action) =>
                action === "test"
                  ? {
                      id: "test",
                      label: t("data.mappingProfiles.runTests"),
                      onSelect: () => void runTests(profile),
                    }
                  : {
                      id: "submit",
                      label: t("data.mappingProfiles.submit"),
                      onSelect: () => setSubmitting(profile),
                    },
              )
          : undefined,
      ),
    // The command handlers read the latest hooks; the columns change with the names and the author.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [templateNames, author],
  );
  const defaultColumns = useMemo(() => initialColumnState(columns), [columns]);
  const [columnState, setColumnState] = useState<GridColumnState>(defaultColumns);
  const source: GridSource<MappingProfile> = {
    queryKey: mappingProfilesKey(),
    fetchPage: fetchMappingProfilesPage,
  };
  const newProfile = author
    ? { label: t("data.mappingProfiles.new"), onAction: () => setCreating(true) }
    : undefined;

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id={headingId} className="text-title-md text-fg-1">
          {t("data.mappingProfiles.title")}
        </h2>
        <span className="flex-1" />
        {newProfile === undefined ? null : (
          <Button variant="primary" onClick={newProfile.onAction}>
            {newProfile.label}
          </Button>
        )}
      </div>
      <div className="flex h-120 min-h-0 flex-col">
        <DataGrid<MappingProfile>
          name="mapping-profiles"
          title={t("data.mappingProfiles.title")}
          titleVisible={false}
          headingLevel={3}
          errorTitle={t("data.mappingProfiles.loadError")}
          countLabel={(value, formatted) =>
            t("data.mappingProfiles.count", { count: value, formatted })
          }
          columns={columns}
          source={source}
          rowKey={(profile) => profile.id}
          rowLabel={(profile) => profile.code}
          testIdPrefix="SF-10"
          rowTestKey={(profile) => `profile-${profile.code}-${String(profile.version_no)}`}
          columnState={columnState}
          defaultColumnState={defaultColumns}
          onColumnStateChange={setColumnState}
          emptyState={
            <EmptyState
              headingLevel={3}
              title={t("data.mappingProfiles.empty.title")}
              description={t("data.mappingProfiles.empty.description")}
              action={newProfile}
            />
          }
        />
      </div>
      {creating ? (
        <NewMappingProfileDrawer
          templates={templates.data ?? []}
          onClose={() => setCreating(false)}
          onSaved={(profile) => {
            setCreating(false);
            toast.show({
              tone: "positive",
              message: t("data.mappingProfiles.saved", {
                code: profile.code,
                version: profile.version_no,
              }),
            });
            void refresh();
          }}
        />
      ) : null}
      {submitting === null ? null : (
        <SubmitProfileModal
          profile={submitting}
          onClose={() => setSubmitting(null)}
          onSubmitted={(profile) => {
            setSubmitting(null);
            toast.show({
              tone: "positive",
              message: t("data.mappingProfiles.submitted", {
                code: profile.code,
                version: profile.version_no,
              }),
            });
            void refresh();
          }}
        />
      )}
    </section>
  );
}

interface EditRow {
  readonly id: number;
  readonly left: string;
  readonly right: string;
}

let nextRowId = 0;

function blankRow(): EditRow {
  nextRowId += 1;
  return { id: nextRowId, left: "", right: "" };
}

function filled(rows: readonly EditRow[]): readonly EditRow[] {
  return rows.filter((row) => row.left.trim() !== "" && row.right.trim() !== "");
}

interface RowsEditorProps {
  readonly title: string;
  readonly columns: readonly [string] | readonly [string, string];
  readonly rows: readonly EditRow[];
  readonly onChange: (rows: readonly EditRow[]) => void;
}

/** A DS-CMP-21 table of text rows with "Add row" and a remove button per row. */
function RowsEditor({ title, columns, rows, onChange }: RowsEditorProps) {
  const update = (id: number, change: Partial<EditRow>) => {
    onChange(rows.map((row) => (row.id === id ? { ...row, ...change } : row)));
  };
  const [first, second] = columns;
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-body-sm font-medium text-fg-1">{title}</legend>
      <table className="w-full border-collapse text-body-sm">
        <caption className="sr-only">{title}</caption>
        <thead>
          <tr className="text-fg-2">
            {columns.map((column) => (
              <th key={column} scope="col" className="py-1 pe-2 text-start font-medium">
                {column}
              </th>
            ))}
            <th scope="col" className="py-1">
              <span className="sr-only">{t("data.mappingProfiles.column.actions")}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.id}>
              <td className="py-1 pe-2">
                <input
                  aria-label={t("data.mappingProfiles.cell", { column: first, row: index + 1 })}
                  className={controlClass(false)}
                  value={row.left}
                  autoComplete="off"
                  spellCheck={false}
                  onChange={(event) => update(row.id, { left: event.target.value })}
                />
              </td>
              {second === undefined ? null : (
                <td className="py-1 pe-2">
                  <input
                    aria-label={t("data.mappingProfiles.cell", { column: second, row: index + 1 })}
                    className={controlClass(false)}
                    value={row.right}
                    autoComplete="off"
                    spellCheck={false}
                    onChange={(event) => update(row.id, { right: event.target.value })}
                  />
                </td>
              )}
              <td className="py-1 text-end">
                <Button
                  variant="ghost"
                  size="sm"
                  icon={Trash}
                  aria-label={t("data.mappingProfiles.removeRow", { row: index + 1 })}
                  onClick={() => onChange(rows.filter((item) => item.id !== row.id))}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div>
        <Button
          variant="secondary"
          size="sm"
          icon={Plus}
          onClick={() => onChange([...rows, blankRow()])}
        >
          {t("data.mappingProfiles.addRow")}
        </Button>
      </div>
    </fieldset>
  );
}

/**
 * The API members the three fields of "New mapping profile" send (DG-FE-06 rev 1.228). The rows of
 * the three editors below them have no field of their own, so what `mappings` is refused for is the
 * banner's.
 */
const PROFILE_MEMBERS = {
  code: ["code"],
  name: ["name"],
  template_code: ["template_code"],
} as const;

interface NewMappingProfileDrawerProps {
  readonly templates: readonly ImportTemplate[];
  readonly onClose: () => void;
  readonly onSaved: (profile: MappingProfile) => void;
}

/** SCREENS §12.4 "New mapping profile": code, name, CSV v2 template, aliases, constants, custom columns. */
function NewMappingProfileDrawer({ templates, onClose, onSaved }: NewMappingProfileDrawerProps) {
  const formId = useId();
  const noAnswer = useNoAnswer();
  const keys = useCommandKeys();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [templateCode, setTemplateCode] = useState<string | null>(null);
  const [aliases, setAliases] = useState<readonly EditRow[]>(() => [blankRow()]);
  const [constants, setConstants] = useState<readonly EditRow[]>(() => [blankRow()]);
  const [custom, setCustom] = useState<readonly EditRow[]>(() => [blankRow()]);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [pending, setPending] = useState(false);
  const refusals = useFieldRefusals(problem, PROFILE_MEMBERS);
  const errors = refusals.fields;
  const options = templates
    .filter((template) => template.family === "CSV_V2")
    .map((template) => ({ value: template.code, label: templateName(template) }));
  const dirty = code !== "" || name !== "" || templateCode !== null;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setPending(true);
    const outcome = await createMappingProfile(keys, {
      code: code.trim(),
      name: name.trim(),
      template_code: templateCode ?? "",
      mappings: {
        aliases: Object.fromEntries(
          filled(aliases).map((row) => [row.left.trim(), row.right.trim()]),
        ),
        constants: Object.fromEntries(
          filled(constants).map((row) => [row.left.trim(), row.right.trim()]),
        ),
        custom_attributes: custom.map((row) => row.left.trim()).filter((value) => value !== ""),
      },
    }).catch(() => null);
    setPending(false);
    if (outcome === null) {
      // No answer: the drawer keeps its input, and the next press sends the same key (DG-FE-05).
      noAnswer();
      return;
    }
    if (!outcome.ok) {
      setProblem(outcome.problem);
      return;
    }
    onSaved(outcome.profile);
  };

  return (
    <Drawer
      open
      wide
      title={t("data.mappingProfiles.new")}
      initialFocus="field"
      dirty={dirty}
      submitting={pending}
      banner={
        refusals.banner === null ? undefined : (
          <RefusalBanner problem={refusals.banner} placed={refusals.placed} />
        )
      }
      primaryAction={{ label: t("data.mappingProfiles.save"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(event) => void submit(event)}
      >
        <Field
          name="profile-code"
          label={t("data.mappingProfiles.field.code")}
          required
          help={t("data.mappingProfiles.field.codeHelp")}
          error={errors.code}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              className={controlClass(errors.code !== null)}
              value={code}
              autoComplete="off"
              spellCheck={false}
              onChange={(event) => {
                setCode(event.target.value);
                refusals.edited("code");
              }}
            />
          )}
        </Field>
        <Field
          name="profile-name"
          label={t("data.mappingProfiles.field.name")}
          required
          error={errors.name}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              className={controlClass(errors.name !== null)}
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                refusals.edited("name");
              }}
            />
          )}
        </Field>
        <Field
          name="profile-template"
          label={t("data.mappingProfiles.field.template")}
          required
          error={errors.template_code}
          width="text"
        >
          {(control) => (
            <Select
              control={control}
              options={options}
              value={templateCode}
              onChange={(next) => {
                setTemplateCode(next);
                refusals.edited("template_code");
              }}
              placeholder={t("data.mappingProfiles.field.templatePlaceholder")}
              invalid={errors.template_code !== null}
            />
          )}
        </Field>
        <RowsEditor
          title={t("data.mappingProfiles.aliases.title")}
          columns={[
            t("data.mappingProfiles.aliases.source"),
            t("data.mappingProfiles.aliases.target"),
          ]}
          rows={aliases}
          onChange={setAliases}
        />
        <RowsEditor
          title={t("data.mappingProfiles.constants.title")}
          columns={[
            t("data.mappingProfiles.constants.column"),
            t("data.mappingProfiles.constants.value"),
          ]}
          rows={constants}
          onChange={setConstants}
        />
        <RowsEditor
          title={t("data.mappingProfiles.custom.title")}
          columns={[t("data.mappingProfiles.custom.column")]}
          rows={custom}
          onChange={setCustom}
        />
      </form>
    </Drawer>
  );
}

interface SubmitProfileModalProps {
  readonly profile: MappingProfile;
  readonly onClose: () => void;
  readonly onSubmitted: (profile: MappingProfile) => void;
}

/** SCREENS §11.0 "Submit for approval" of a TESTED version (`MAPPING_PROFILE_VERSION`). */
function SubmitProfileModal({ profile, onClose, onSubmitted }: SubmitProfileModalProps) {
  const noAnswer = useNoAnswer();
  const keys = useCommandKeys();
  const [comment, setComment] = useState("");
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const submit = async () => {
    setPending(true);
    const outcome = await submitMappingProfile(
      keys,
      profile.id,
      comment.trim() === "" ? null : comment.trim(),
    ).catch(() => null);
    setPending(false);
    if (outcome === null) {
      noAnswer();
      return;
    }
    if (!outcome.ok) {
      setProblem(outcome.problem);
      return;
    }
    onSubmitted(outcome.profile);
  };
  return (
    <Modal
      open
      variant="form"
      title={t("data.mappingProfiles.submitTitle", {
        code: profile.code,
        version: profile.version_no,
      })}
      primaryAction={{ label: t("data.mappingProfiles.submit"), onAction: () => void submit() }}
      submitting={pending}
      onClose={onClose}
    >
      {problem === null ? null : <Banner tone="negative" title={problemText(problem)} />}
      <Field name="profile-submit-comment" label={t("data.mappingProfiles.comment")} optional>
        {(control) => (
          <textarea
            {...control}
            rows={3}
            className={controlClass(false, true)}
            value={comment}
            onChange={(event) => setComment(event.target.value)}
          />
        )}
      </Field>
    </Modal>
  );
}
