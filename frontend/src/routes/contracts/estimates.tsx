// SF-03:estimates Estimates workbench (SCREENS §8; §0.4 RT-12, RT-13; DESIGN_SYSTEM DS-CMP-08,
// DS-CMP-09, DS-CMP-23; 04 API-R-32 `GET, POST /contracts/{id}/estimates`,
// `GET /estimates/{id}/versions`, API-R-39 `GET /exceptions`; PRD ACT-11, POL-042; BUILD_SPEC CTR-25).
// The master list of the contract's estimated elements, grouped under their E-09 kind, beside the
// detail of the element in the route (`estimate.tsx`); "Add estimated element" opens the element
// drawer and then the drawer of the element's first version.
//
// `GET /contracts/{id}/estimates` answers the summaries of an element's current and latest version
// without their figures, so the key figure of a row comes from the versions of its element (one read
// per element, shared with the detail). "Reassessment due" binds the open `VC_REASSESSMENT_MISSING`
// item whose `business_key` is the element code.
import { useQueries, useQuery } from "@tanstack/react-query";
import { useId, useMemo, useState } from "react";
import { useLocation, useMatch, useNavigate } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Field } from "../../components/form/Field";
import { MultiSelect } from "../../components/form/MultiSelect";
import { Plus, WarningCircle } from "../../components/icons/registry";
import { type MasterItem, MasterDetail } from "../../components/record/MasterDetail";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { chipFor, StatusChip, ToneChip } from "../../components/ui/StatusChip";
import { testIdKey } from "../../components/data-grid/DataGrid";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { ApiProblem } from "../../lib/api/problems";
import { type Contract, JUDGEMENT_CREATE_PERMISSION } from "../../lib/api/queries/contracts";
import {
  contractEstimatesKey,
  contractEstimatesPath,
  currentAndLatest,
  type Estimate,
  ESTIMATE_CREATE_PERMISSION,
  ESTIMATE_KINDS,
  ESTIMATE_METHODS,
  ESTIMATE_RECORD_KEYS,
  ESTIMATE_ROUTE,
  ESTIMATE_TARGETS,
  type EstimateKind,
  type EstimateMethod,
  estimateRoute,
  type EstimateTarget,
  estimateVersionsKey,
  fetchEstimates,
  fetchEstimateVersions,
  fetchReassessmentDue,
  reassessmentKey,
  VC_ELEMENT_TYPES,
  type VcElementType,
} from "../../lib/api/queries/estimates";
import type { Obligation } from "../../lib/api/queries/obligations";
import {
  fetchPeriods,
  periodLabel as calendarLabel,
  periodsKey,
} from "../../lib/api/queries/tenant";
import {
  buildElement,
  defaultMethod,
  type ElementForm,
  EMPTY_ELEMENT,
  keyFigure,
} from "../../lib/forms/estimate";
import { formatDate, formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { type Choice, fieldError, RadioGroup, SelectField, TextField } from "./drawers/common";
import { EstimatePane, type EstimatePaneTab, isEstimatePane } from "./estimate";
import {
  elementTypeLabel,
  type Failure,
  FailureNotice,
  figureText,
  kindLabel,
  methodLabel,
  type PeriodLabel,
} from "./estimate-parts";
import type { WorkbenchTabProps } from "./tabs/schedules";

const ELEMENT_FIELDS = [
  "estimate_kind",
  "element_code",
  "vc_element_type",
  "method",
  "obligation_key",
  "allocation_target",
  "target_obligation_keys",
  "allocation_criteria_evidence",
] as const;
/** The option of the "Obligation" select that names none: the element belongs to the contract. */
const WHOLE_CONTRACT = "";

function ElementDrawer({
  contract,
  obligations,
  onClose,
  onAdded,
}: {
  readonly contract: Contract;
  readonly obligations: readonly Obligation[];
  readonly onClose: () => void;
  readonly onAdded: (estimate: Estimate) => void;
}) {
  const formId = useId();
  const [form, setForm] = useState<ElementForm>(EMPTY_ELEMENT);
  const [attempted, setAttempted] = useState(false);
  const [unreached, setUnreached] = useState(false);
  const create = useCommand<Estimate>({
    method: "POST",
    path: contractEstimatesPath(contract.id),
    invalidates: ESTIMATE_RECORD_KEYS,
  });
  const built = useMemo(() => buildElement(form), [form]);
  const failure: Failure | null = unreached ? "unreached" : create.problem;
  const shown = (name: (typeof ELEMENT_FIELDS)[number]) =>
    (attempted ? built.errors[name] : undefined) ?? fieldError(create.problem, name);
  const change = (next: ElementForm) => {
    setForm(next);
    setUnreached(false);
  };
  const obligationChoices: readonly Choice<string>[] = [
    { value: WHOLE_CONTRACT, label: t("contracts.estimates.element.noObligation") },
    ...obligations.map((item) => ({
      value: item.obligation_key,
      label: `${item.obligation_key} · ${item.product.name}`,
    })),
  ];
  const variable = form.kind === "VARIABLE_CONSIDERATION";

  const submit = async () => {
    setAttempted(true);
    if (built.body === null) {
      return;
    }
    setUnreached(false);
    const outcome = await create.submit(built.body);
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      onAdded(outcome.data);
    } else {
      setUnreached(outcome.kind === "network-error");
    }
  };

  return (
    <Drawer
      open
      title={t("contracts.estimates.add")}
      subtitle={contract.external_id}
      initialFocus="field"
      dirty={form !== EMPTY_ELEMENT}
      submitting={create.pending}
      banner={<FailureNotice failure={failure} fields={ELEMENT_FIELDS} />}
      primaryAction={{ label: t("contracts.estimates.element.add"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-03-drawer-estimate-element"
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <SelectField<EstimateKind>
          name="estimate_kind"
          label={t("contracts.estimates.element.kind")}
          options={ESTIMATE_KINDS.map((kind) => ({ value: kind, label: kindLabel(kind) }))}
          value={form.kind}
          onChange={(kind) =>
            change({
              ...form,
              kind,
              method: defaultMethod(kind),
              vcElementType: kind === "VARIABLE_CONSIDERATION" ? form.vcElementType : null,
            })
          }
          error={shown("estimate_kind")}
        />
        <TextField
          name="element_code"
          label={t("contracts.estimates.element.code")}
          value={form.elementCode}
          onChange={(elementCode) => change({ ...form, elementCode })}
          required
          help={t("contracts.estimates.element.codeHelp")}
          error={shown("element_code")}
        />
        {variable ? (
          <SelectField<VcElementType>
            name="vc_element_type"
            label={t("contracts.estimates.element.vcType")}
            options={VC_ELEMENT_TYPES.map((type) => ({
              value: type,
              label: elementTypeLabel(type),
            }))}
            value={form.vcElementType}
            onChange={(vcElementType) => change({ ...form, vcElementType })}
            error={shown("vc_element_type")}
          />
        ) : null}
        <SelectField<EstimateMethod>
          name="method"
          label={t("contracts.estimates.element.method")}
          options={ESTIMATE_METHODS.map((method) => ({
            value: method,
            label: methodLabel(method),
          }))}
          value={form.method}
          onChange={(method) => change({ ...form, method })}
          error={shown("method")}
        />
        <p className="-mt-2 text-body-sm text-fg-3">{t("contracts.estimates.methodLocked")}</p>
        <SelectField<string>
          name="obligation_key"
          label={t("contracts.estimates.element.obligation")}
          options={obligationChoices}
          value={form.obligationKey ?? WHOLE_CONTRACT}
          onChange={(key) =>
            change({ ...form, obligationKey: key === WHOLE_CONTRACT ? null : key })
          }
          optional
          error={shown("obligation_key")}
        />
        <RadioGroup<EstimateTarget>
          legend={t("contracts.estimates.element.target")}
          options={ESTIMATE_TARGETS.map((target) => ({
            value: target,
            label: t(`contracts.estimates.target.${target}`),
          }))}
          value={form.target}
          onChange={(target) =>
            change({ ...form, target, targetKeys: target === "OBLIGATIONS" ? form.targetKeys : [] })
          }
          error={shown("allocation_target")}
        />
        {form.target === "OBLIGATIONS" ? (
          <Field
            name="target_obligation_keys"
            label={t("contracts.estimates.element.targetObligations")}
            required
            error={shown("target_obligation_keys")}
            width="text"
          >
            {(control) => (
              <MultiSelect<string>
                control={control}
                options={obligations.map((item) => ({
                  value: item.obligation_key,
                  label: `${item.obligation_key} · ${item.product.name}`,
                }))}
                values={form.targetKeys}
                onChange={(targetKeys) => change({ ...form, targetKeys })}
                invalid={shown("target_obligation_keys") !== null}
              />
            )}
          </Field>
        ) : null}
        {form.target === "CONTRACT" ? null : (
          <TextField
            name="allocation_criteria_evidence"
            label={t("contracts.estimates.element.criteriaEvidence")}
            value={form.criteriaEvidence}
            onChange={(criteriaEvidence) => change({ ...form, criteriaEvidence })}
            required
            help={t("contracts.estimates.element.criteriaHelp")}
            error={shown("allocation_criteria_evidence")}
            width="full"
            multiline
          />
        )}
      </form>
    </Drawer>
  );
}

function matches(element: Estimate, filter: string): boolean {
  const query = filter.trim().toLocaleLowerCase();
  return (
    query === "" ||
    element.element_code.toLocaleLowerCase().includes(query) ||
    kindLabel(element.estimate_kind).toLocaleLowerCase().includes(query)
  );
}

export function EstimatesTab({ contract, context, obligations, me, ctxSearch }: WorkbenchTabProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const headingId = useId();
  const estimateId = useMatch(ESTIMATE_ROUTE)?.params.estimateId ?? null;
  const search = new URLSearchParams(location.search);
  const paneParam = search.get("pane");
  const tab: EstimatePaneTab = isEstimatePane(paneParam) ? paneParam : "current";
  const contextPeriod = search.get("period");
  const [filter, setFilter] = useState("");
  const [adding, setAdding] = useState(false);
  // The element that was just added: its detail opens the drawer of version 1.
  const [started, setStarted] = useState<string | null>(null);

  // SCREENS §0.6 SCR-PERM-02 (a): an estimate is a record of the contract's legal entity, so its
  // commands are offered where the permission is held for that entity.
  const access = useAccess();
  const canPrepare =
    context.knownAt === null &&
    access.holds(ESTIMATE_CREATE_PERMISSION, contract.contracting_entity);
  const canJudge = access.holds(JUDGEMENT_CREATE_PERMISSION, contract.contracting_entity);

  const estimates = useQuery({
    queryKey: contractEstimatesKey(contract.id),
    queryFn: () => fetchEstimates(contract.id),
  });
  const elements = useMemo(() => {
    const order = new Map(ESTIMATE_KINDS.map((kind, index) => [kind, index]));
    return [...(estimates.data ?? [])].sort(
      (left, right) =>
        (order.get(left.estimate_kind) ?? 0) - (order.get(right.estimate_kind) ?? 0) ||
        left.element_code.localeCompare(right.element_code, undefined, { numeric: true }),
    );
  }, [estimates.data]);
  const versionReads = useQueries({
    queries: elements.map((element) => ({
      queryKey: estimateVersionsKey(element.id),
      queryFn: () => fetchEstimateVersions(element.id),
    })),
  });
  const due = useQuery({
    queryKey: reassessmentKey(contract.id),
    queryFn: () => fetchReassessmentDue(contract.id),
    retry: false,
  });
  const entity = contract.contracting_entity.code;
  const periods = useQuery({
    queryKey: periodsKey({ entity }),
    queryFn: () => fetchPeriods({ entity }),
    retry: false,
  });
  const periodLabel = useMemo((): PeriodLabel => {
    const labels = new Map<string, string>();
    for (const row of periods.data ?? []) {
      try {
        labels.set(row.period.period_key, calendarLabel(row.period));
      } catch {
        // A period the format module cannot label reads as its key.
      }
    }
    return (key) => labels.get(key) ?? key;
  }, [periods.data]);
  const periodEnd = (match: (row: NonNullable<typeof periods.data>[number]) => boolean) =>
    (periods.data ?? []).find(match)?.period.end_date ?? null;
  const dueOf = (element: Estimate) =>
    (due.data ?? []).find((item) => item.business_key === element.element_code) ?? null;

  const paneSearch = (next: EstimatePaneTab) => {
    const params = new URLSearchParams(ctxSearch);
    if (next !== "current") {
      params.set("pane", next);
    }
    const text = params.toString();
    return text === "" ? "" : `?${text}`;
  };

  const shownElements = elements.filter((element) => matches(element, filter));
  const items: MasterItem[] = shownElements.map((element) => {
    const read = versionReads[elements.indexOf(element)];
    const { latest } = currentAndLatest(read?.data ?? []);
    const summary = element.latest_version;
    const chip = summary === null ? null : chipFor("E-12", summary.status);
    return {
      id: element.id,
      name: element.element_code,
      mono: true,
      group: kindLabel(element.estimate_kind),
      amount:
        latest === null ? undefined : (
          <span className="num text-body text-fg-1">
            {figureText(keyFigure(element.estimate_kind, latest), latest.currency)}
          </span>
        ),
      chips: (
        <>
          {summary === null ? (
            <span className="text-body-sm">{t("contracts.estimates.row.noVersion")}</span>
          ) : (
            <span className="num text-body-sm">
              {t("contracts.estimates.row.version", {
                version: formatNumber(summary.version_no, { kind: "count" }),
                date: formatDate(summary.effective_date),
              })}
            </span>
          )}
          {chip === null ? null : <StatusChip status={chip.status} />}
          {dueOf(element) === null ? null : (
            <ToneChip
              tone="warning"
              icon={WarningCircle}
              label={t("contracts.estimates.reassessmentDue")}
            />
          )}
        </>
      ),
      testId: `SF-03-row-${testIdKey(element.element_code)}`,
    };
  });
  const selected = elements.find((element) => element.id === estimateId) ?? null;
  const selectedDue = selected === null ? null : dueOf(selected);
  const notFound = estimateId !== null && estimates.isSuccess && selected === null;

  return (
    <section aria-labelledby={headingId} className="flex min-h-120 flex-col">
      <h2 id={headingId} className="sr-only">
        {t("contracts.workbench.tabs.estimates")}
      </h2>
      <div className="min-h-120 rounded-md border border-hairline bg-surface">
        <MasterDetail
          type="estimates"
          listLabel={t("contracts.estimates.list")}
          listTestId="SF-03-grid-estimates"
          items={items}
          selectedId={estimateId}
          onSelect={(id) => void navigate(`${estimateRoute(contract.id, id)}${paneSearch(tab)}`)}
          status={estimates.isPending ? "loading" : estimates.isError ? "error" : "ready"}
          errorState={
            <Banner
              tone="negative"
              title={t("contracts.estimates.loadError")}
              actions={
                <Button variant="link" onClick={() => void estimates.refetch()}>
                  {t("common.grid.retry")}
                </Button>
              }
            >
              {estimates.error instanceof ApiProblem ? <p>{estimates.error.title}</p> : null}
            </Banner>
          }
          emptyState={
            elements.length === 0 ? (
              <EmptyState
                title={t("contracts.estimates.emptyTitle")}
                description={t("contracts.estimates.emptyDescription")}
                headingLevel={3}
                action={
                  canPrepare
                    ? { label: t("contracts.estimates.add"), onAction: () => setAdding(true) }
                    : undefined
                }
              />
            ) : (
              <p className="py-3 text-body-sm text-fg-2">{t("contracts.estimates.noMatch")}</p>
            )
          }
          toolbar={
            <div className="flex w-full flex-col gap-1.5">
              <div className="flex items-center gap-2">
                <input
                  type="search"
                  aria-label={t("contracts.estimates.filter")}
                  placeholder={t("contracts.estimates.filter")}
                  value={filter}
                  onChange={(event) => setFilter(event.target.value)}
                  className="h-[var(--control-h-sm)] min-w-0 flex-1 rounded-md border border-control bg-surface px-2 text-body-sm text-fg-1 placeholder:text-fg-3"
                />
                {canPrepare ? (
                  <Button variant="secondary" size="sm" icon={Plus} onClick={() => setAdding(true)}>
                    {t("contracts.estimates.add")}
                  </Button>
                ) : null}
              </div>
              <p className="text-caption text-fg-3">
                {t("contracts.estimates.caption", {
                  count: elements.length,
                  formatted: formatNumber(elements.length, { kind: "count" }),
                })}
              </p>
            </div>
          }
          detailLabel={t("contracts.estimates.detail", { code: selected?.element_code ?? "" })}
          noSelection={t("contracts.estimates.noSelection")}
          detailTestId="SF-03-pane-estimate"
        >
          {selected === null ? (
            notFound ? (
              <p className="p-[var(--panel-pad)] text-body text-fg-1">
                {t("contracts.estimates.notFound")}
              </p>
            ) : null
          ) : (
            <EstimatePane
              key={selected.id}
              contract={contract}
              estimate={selected}
              canPrepare={canPrepare}
              canJudge={canJudge}
              viewerId={me.user.id}
              due={selectedDue}
              duePeriodEnd={
                selectedDue === null
                  ? null
                  : periodEnd((row) => row.period.id === selectedDue.period_id)
              }
              contextPeriod={contextPeriod}
              contextPeriodEnd={periodEnd((row) => row.period.period_key === contextPeriod)}
              periodLabel={periodLabel}
              tab={tab}
              onTabChange={(next) =>
                void navigate(`${estimateRoute(contract.id, selected.id)}${paneSearch(next)}`, {
                  replace: true,
                })
              }
              startVersion={started === selected.id}
              onVersionStarted={() => setStarted(null)}
              ctxSearch={ctxSearch}
              commands={context.knownAt === null}
            />
          )}
        </MasterDetail>
      </div>
      {adding ? (
        <ElementDrawer
          contract={contract}
          obligations={obligations}
          onClose={() => setAdding(false)}
          onAdded={(estimate) => {
            setAdding(false);
            setStarted(estimate.id);
            void navigate(`${estimateRoute(contract.id, estimate.id)}${paneSearch("current")}`);
          }}
        />
      ) : null}
    </section>
  );
}
