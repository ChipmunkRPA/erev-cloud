// SF-14:access-reviews Access reviews (SCREENS_B §9.13; SCREENS §0.4 RT-90, §0.3 SCR-IA-03, §0.7
// SCR-PERM-01, SCR-ST-03, §0.4 E-107; DESIGN_SYSTEM DS-CMP-10, DS-CMP-11, DS-CMP-19, DS-CMP-21, DS-CMP-23;
// 04 API-R-51 `GET, POST /access-reviews`, API-R-05 `GET /users`, API-R-06 `GET /roles`; T-PLT-40;
// REQ-CTL-006; BUILD_SPEC WEB-21). The Settings frame with the Access route tabs and the DataGrid
// "Campaigns" (name, E-107 chip, as of, reviewers, members, decided "<n> of <m>", revocations completed,
// started, completed). "New campaign" (`access.approve`) takes Name, As of (a business date and a UTC
// time) and Reviewers, offering only the members whose current roles hold `access.approve`; the created
// campaign opens, where "Start review" follows. The empty state reads "No access reviews yet" with the
// primary "New campaign".
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useId, useMemo, useState } from "react";
import { useNavigate } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import { type GridColumn, type GridSource } from "../../components/data-grid/types";
import { AccessLimited } from "../../components/feedback/AccessLimited";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { DateInput } from "../../components/form/DateInput";
import { controlClass, Field } from "../../components/form/Field";
import { MultiSelect } from "../../components/form/MultiSelect";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { useCommand } from "../../lib/api/commands";
import {
  ACCESS_APPROVE_PERMISSION,
  type AccessReview,
  type AccessReviewCreate,
  ACCESS_REVIEWS_PATH,
  accessReviewsKey,
  decidedCount,
  EVERY_ACCESS_REVIEW,
  fetchAccessReviewsPage,
  reviewRoute,
} from "../../lib/api/queries/access-reviews";
import { useAccess } from "../../lib/access";
import { type Me, useMe } from "../../lib/api/queries/me";
import { placeProblem } from "../../lib/api/refusals";
import { permissionsOf, type Role, useActiveRoles } from "../../lib/api/queries/roles";
import { currentRoles, fetchUsersPage, type UserItem, usersKey } from "../../lib/api/queries/users";
import { formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { SettingsPageHeader } from "../settings/index";

function statusChip(review: AccessReview): string {
  return chipFor("E-107", review.status)?.status ?? review.status;
}

function count(value: number): string {
  return formatNumber(value, { kind: "count" });
}

function mono(text: string) {
  return <span className="num">{text}</span>;
}

/** SCREENS_B §9.13 campaign grid columns. */
// API-C-09 sort keys: GET /api/v1/access-reviews
export function campaignColumns(): readonly GridColumn<AccessReview>[] {
  return [
    {
      id: "name",
      header: t("access.reviews.column.name"),
      kind: "identifier",
      value: (review) => review.name,
      href: (review) => reviewRoute(review.id),
      sortKey: "name",
      width: 240,
    },
    {
      id: "status",
      header: t("access.reviews.column.status"),
      kind: "status",
      value: (review) => review.status,
      render: (review) => <StatusChip status={statusChip(review)} />,
    },
    {
      id: "as_of",
      header: t("access.reviews.column.asOf"),
      kind: "timestamp",
      value: (review) => review.as_of,
      sortKey: "as_of",
    },
    {
      id: "reviewers",
      header: t("access.reviews.column.reviewers"),
      kind: "text",
      value: (review) => review.reviewers.map((reviewer) => reviewer.display_name).join(", "),
      width: 200,
    },
    {
      id: "members",
      header: t("access.reviews.column.members"),
      kind: "number",
      numberKind: "count",
      value: (review) => String(review.counts.members),
      width: 104,
    },
    {
      id: "decided",
      header: t("access.reviews.column.decided"),
      kind: "text",
      value: (review) =>
        t("access.reviews.decided", {
          decided: count(decidedCount(review.counts)),
          members: count(review.counts.members),
        }),
      render: (review) =>
        mono(
          t("access.reviews.decided", {
            decided: count(decidedCount(review.counts)),
            members: count(review.counts.members),
          }),
        ),
      width: 112,
    },
    {
      id: "revoked",
      header: t("access.reviews.column.revocationsCompleted"),
      kind: "number",
      numberKind: "count",
      value: (review) => String(review.counts.revoked),
      width: 176,
    },
    {
      id: "started_at",
      header: t("access.reviews.column.started"),
      kind: "timestamp",
      value: (review) => review.started_at,
    },
    {
      id: "completed_at",
      header: t("access.reviews.column.completed"),
      kind: "timestamp",
      value: (review) => review.completed_at,
    },
  ];
}

export function AccessReviewsScreen() {
  const me = useMe();
  const access = useAccess();
  const title = t("access.reviews.title");
  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={6} />;
  } else if (!access.holdsForAll(ACCESS_APPROVE_PERMISSION)) {
    // A campaign reviews the members of the whole workspace: its list, and every act on one, are
    // read and done by a holder of `access.approve` for all entities (04 T-PLT-40; SCREENS §0.6
    // SCR-PERM-02 (c)).
    body = (
      <AccessLimited
        area={title}
        permissions={[ACCESS_APPROVE_PERMISSION]}
        allEntities={
          access.holdsAnywhere(ACCESS_APPROVE_PERMISSION)
            ? {
                message: "access.reviews.access.allEntities",
                permission: ACCESS_APPROVE_PERMISSION,
              }
            : undefined
        }
      />
    );
  } else {
    return <AccessReviewsPage me={me.data} />;
  }
  return (
    <div
      data-testid="SF-14-access-reviews-page"
      className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="access" />
      {body}
    </div>
  );
}

function AccessReviewsPage({ me }: { readonly me: Me }) {
  const [creating, setCreating] = useState(false);
  const [total, setTotal] = useState<number | undefined>(undefined);
  const title = t("access.reviews.title");
  const columns = useMemo(() => campaignColumns(), []);
  const query = { status: [] as readonly string[] };
  const source: GridSource<AccessReview> = {
    queryKey: accessReviewsKey(query),
    fetchPage: (cursor, sort) => fetchAccessReviewsPage(query, cursor, sort),
  };
  const newCampaign = {
    label: t("access.reviews.new.title"),
    onAction: () => {
      setCreating(true);
    },
  };
  return (
    <div
      data-testid="SF-14-access-reviews-page"
      className="flex h-full min-h-0 w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="access">
        {total === undefined ? null : (
          <p className="num text-body-sm text-fg-3">
            {t("access.reviews.count", { count: total, formatted: count(total) })}
          </p>
        )}
      </SettingsPageHeader>
      <div className="flex min-h-0 flex-1 flex-col">
        <DataGrid<AccessReview>
          name="access-reviews"
          title={t("access.reviews.grid")}
          errorTitle={t("access.reviews.loadError")}
          countLabel={(value, formatted) => t("access.reviews.count", { count: value, formatted })}
          columns={columns}
          source={source}
          rowKey={(review) => review.id}
          rowLabel={(review) => review.name}
          rowHref={(review) => reviewRoute(review.id)}
          testIdPrefix="SF-14"
          rowTestKey={(review) => review.name}
          onTotalChange={(next) => setTotal(next?.count)}
          toolbarActions={
            <Button variant="primary" onClick={newCampaign.onAction}>
              {newCampaign.label}
            </Button>
          }
          emptyState={
            <div data-testid="SF-14-empty-access-reviews">
              <EmptyState
                title={t("access.reviews.empty.title")}
                description={t("access.reviews.empty.description")}
                action={newCampaign}
              />
            </div>
          }
        />
      </div>
      {creating ? (
        <NewCampaignModal
          me={me}
          onClose={() => {
            setCreating(false);
          }}
        />
      ) : null}
    </div>
  );
}

/**
 * Members who hold `access.approve` for all entities by a role of their own (SCREENS_B §9.13
 * "Reviewers"): a campaign is the workspace's, and the API takes no other reviewer (04 T-PLT-40).
 */
export function reviewerCandidates(
  users: readonly UserItem[],
  roles: readonly Pick<Role, "id" | "permissions">[],
): readonly UserItem[] {
  return users.filter(
    (user) =>
      user.status === "ACTIVE" &&
      permissionsOf(
        currentRoles(user)
          .filter((role) => role.is_all_entities)
          .map((role) => role.role.id),
        roles,
      ).has(ACCESS_APPROVE_PERMISSION),
  );
}

// docs/dev-guide.md DG-FE-06: the fields of "New campaign" and the members of the body each sends. The
// time of day is a part of `as_of` and shows no message of its own.
const CAMPAIGN_MEMBERS = {
  name: ["name"],
  asOf: ["as_of"],
  reviewers: ["reviewer_membership_ids"],
} as const;

/** SCREENS_B §9.13 "New campaign" form modal. */
export function NewCampaignModal({
  me,
  onClose,
}: {
  readonly me: Me;
  readonly onClose: () => void;
}) {
  const formId = useId();
  const toast = useToast();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [dateText, setDateText] = useState("");
  const [date, setDate] = useState<string | null>(null);
  const [time, setTime] = useState("00:00");
  const [reviewers, setReviewers] = useState<readonly string[]>(() =>
    [me.active_membership_id ?? ""].filter((id) => id !== ""),
  );
  const [attempted, setAttempted] = useState(false);
  const usersQuery = { status: ["ACTIVE"], q: null };
  const users = useQuery({
    queryKey: usersKey(usersQuery),
    queryFn: async () => (await fetchUsersPage(usersQuery, null, null)).items,
  });
  const roles = useActiveRoles();
  const candidates = useMemo(
    () => reviewerCandidates(users.data ?? [], roles.data ?? []),
    [users.data, roles.data],
  );
  const create = useCommand<AccessReview>({
    method: "POST",
    path: ACCESS_REVIEWS_PATH,
    invalidates: [EVERY_ACCESS_REVIEW],
  });
  const placed = useMemo(() => placeProblem(create.problem, CAMPAIGN_MEMBERS), [create.problem]);
  const nameError = attempted && name.trim() === "" ? t("access.reviews.new.nameRequired") : null;
  const dateError = attempted && date === null ? t("access.reviews.new.asOfRequired") : null;
  const reviewersError =
    attempted && reviewers.length === 0 ? t("access.reviews.new.reviewersRequired") : null;

  const submit = async () => {
    setAttempted(true);
    if (name.trim() === "" || date === null || reviewers.length === 0) {
      return;
    }
    const body: AccessReviewCreate = {
      name: name.trim(),
      as_of: `${date}T${time === "" ? "00:00" : time}:00Z`,
      reviewer_membership_ids: [...reviewers],
    };
    const outcome = await create.submit(body);
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      toast.show({
        tone: "positive",
        message: t("access.reviews.new.created", { name: outcome.data.name }),
      });
      onClose();
      void navigate(reviewRoute(outcome.data.id));
    }
  };

  return (
    <Modal
      open
      variant="form"
      title={t("access.reviews.new.title")}
      primaryAction={{ label: t("access.reviews.new.submit"), form: formId }}
      submitting={create.pending}
      onClose={onClose}
      testId="SF-14-dialog-new-campaign"
    >
      <form
        id={formId}
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <RefusalBanner problem={create.problem} placed={placed} />
        <Field
          name="campaign-name"
          label={t("access.reviews.new.name")}
          required
          error={placed.fields.name ?? nameError}
        >
          {(control) => (
            <input
              {...control}
              type="text"
              autoComplete="off"
              value={name}
              onChange={(event) => {
                setName(event.target.value);
              }}
              className={controlClass(control["aria-invalid"] === true)}
            />
          )}
        </Field>
        <div className="flex flex-wrap gap-4">
          <Field
            name="campaign-as-of"
            label={t("access.reviews.new.asOfDate")}
            required
            width="date"
            error={placed.fields.asOf ?? dateError}
          >
            {(control) => (
              <DateInput
                control={control}
                value={dateText}
                onChange={setDateText}
                onValue={setDate}
                invalid={control["aria-invalid"] === true}
              />
            )}
          </Field>
          <Field
            name="campaign-as-of-time"
            label={t("access.reviews.new.asOfTime")}
            help={t("access.reviews.new.asOfTimeHelp")}
          >
            {(control) => (
              <input
                {...control}
                type="time"
                value={time}
                onChange={(event) => {
                  setTime(event.target.value);
                }}
                className={controlClass(false)}
              />
            )}
          </Field>
        </div>
        <Field
          name="campaign-reviewers"
          label={t("access.reviews.new.reviewers")}
          required
          help={t("access.reviews.new.reviewersHelp")}
          error={placed.fields.reviewers ?? reviewersError}
        >
          {(control) => (
            <MultiSelect
              control={control}
              options={candidates.map((user) => ({
                value: user.id,
                label: `${user.display_name} · ${user.email}`,
              }))}
              values={reviewers}
              invalid={reviewersError !== null}
              onChange={setReviewers}
            />
          )}
        </Field>
      </form>
    </Modal>
  );
}
