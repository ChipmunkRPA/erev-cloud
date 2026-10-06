// SF-14:access-review Campaign (SCREENS_B §9.13; SCREENS §0.4 RT-109, §0.4 E-107, E-108 chips; DESIGN_SYSTEM
// DS-CMP-06, DS-CMP-10, DS-CMP-11, DS-CMP-19; 04 API-R-51 `GET /access-reviews/{id}`, `/start`,
// `/complete`, `/cancel`, `GET /access-reviews/{id}/items`, `POST …/items/{item_id}/decide`,
// `…/confirm-revocation`; API-R-12 `GET /files/{id}/content`; T-PLT-40, T-PLT-41; REQ-CTL-006; DB-10;
// BUILD_SPEC WEB-21). The record header (name, E-107 chip, as of, reviewers) with "Download snapshot",
// "Start review" on a draft, "Cancel campaign" and the primary "Complete campaign", which refuses while
// items are pending ("Decide <n> pending items before completing the campaign."); the KPI strip Members,
// Certified, Revocations requested, Revocations completed, Pending; the DataGrid "Items" with the roles
// at snapshot, last login, first grant, grantors and the decision: "Certify <member>" and "Request
// revocation for <member>" (a comment of at least 10 characters) on a pending row, "Confirm revocation"
// on a requested one, and "You cannot review your own access." on the reviewer's own row (DB-10).
import { type ReactNode, useId, useMemo, useState } from "react";
import { useParams } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import { type GridColumn, type GridSource } from "../../components/data-grid/types";
import { AccessLimited } from "../../components/feedback/AccessLimited";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { ReasonField, reasonError } from "../../components/form/ReasonField";
import { KpiStrip } from "../../components/record/KpiStrip";
import { RecordHeader } from "../../components/record/RecordHeader";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { useCommand } from "../../lib/api/commands";
import {
  ACCESS_APPROVE_PERMISSION,
  type AccessReview,
  type AccessReviewDecide,
  type AccessReviewItem,
  ACCESS_REVIEWS_ROUTE,
  earliestGrant,
  EVERY_ACCESS_REVIEW,
  fetchReviewItemsPage,
  fileContentPath,
  grantors,
  itemConfirmRevocationPath,
  itemDecidePath,
  type ReviewAction,
  reviewActionPath,
  reviewItemsKey,
  reviewKey,
  rolesSnapshotText,
  useReview,
} from "../../lib/api/queries/access-reviews";
import { useAccess } from "../../lib/access";
import { type Me, useMe } from "../../lib/api/queries/me";
import { formatNumber, formatTimestamp, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { SETTINGS_PATH } from "../settings/index";

function count(value: number): string {
  return formatNumber(value, { kind: "count" });
}

/** SCREENS §0.4 E-108 chip word of an item decision. */
export function decisionChip(decision: AccessReviewItem["decision"]): string {
  return chipFor("E-108", decision)?.status ?? decision;
}

export function AccessReviewPage() {
  const { reviewId = "" } = useParams();
  const me = useMe();
  const access = useAccess();
  // A campaign is read by a holder of `access.approve` for all entities (04 T-PLT-40): without
  // it no read is sent.
  const allowed = access.holdsForAll(ACCESS_APPROVE_PERMISSION);
  const review = useReview(reviewId, allowed);
  const title = t("access.review.title");
  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={6} />;
  } else if (!allowed) {
    body = (
      <AccessLimited
        area={t("access.reviews.title")}
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
  } else if (review.isError) {
    body = (
      <Banner tone="negative" title={t("access.review.loadError")}>
        {review.error.message}
      </Banner>
    );
  } else if (review.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={6} />;
  } else {
    return <ReviewRecord me={me.data} review={review.data} />;
  }
  return (
    <div
      data-testid="SF-14-access-review-page"
      className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      {body}
    </div>
  );
}

type Dialog =
  | { readonly kind: "none" }
  | { readonly kind: "action"; readonly action: ReviewAction }
  | { readonly kind: "revoke"; readonly item: AccessReviewItem }
  | { readonly kind: "confirm-revocation"; readonly item: AccessReviewItem };

function ReviewRecord({ me, review }: { readonly me: Me; readonly review: AccessReview }) {
  const [dialog, setDialog] = useState<Dialog>({ kind: "none" });
  const [pendingNotice, setPendingNotice] = useState(false);
  const close = () => {
    setDialog({ kind: "none" });
  };
  const chip = chipFor("E-107", review.status);
  const inReview = review.status === "IN_REVIEW";
  const actions: ReactNode[] = [];
  if (review.snapshot_file_id !== null) {
    actions.push(
      <a
        key="snapshot"
        href={fileContentPath(review.snapshot_file_id)}
        download
        className="inline-flex h-[var(--control-h)] items-center justify-center whitespace-nowrap rounded-md border border-control bg-surface px-3 text-body-sm font-medium text-fg-1 hover:bg-hover active:bg-active"
      >
        {t("access.review.downloadSnapshot")}
      </a>,
    );
  }
  if (review.status === "DRAFT") {
    actions.push(
      <Button
        key="start"
        variant="primary"
        onClick={() => setDialog({ kind: "action", action: "start" })}
      >
        {t("access.review.start")}
      </Button>,
    );
  }
  if (review.status === "DRAFT" || inReview) {
    actions.push(
      <Button
        key="cancel"
        variant="ghost"
        onClick={() => setDialog({ kind: "action", action: "cancel" })}
      >
        {t("access.review.cancel")}
      </Button>,
    );
  }
  const complete = inReview ? (
    <Button
      key="complete"
      variant="primary"
      onClick={() => {
        if (review.counts.pending > 0) {
          setPendingNotice(true);
          return;
        }
        setDialog({ kind: "action", action: "complete" });
      }}
    >
      {t("access.review.complete")}
    </Button>
  ) : null;
  if (complete !== null) {
    actions.push(complete);
  }

  return (
    <div
      data-testid="SF-14-access-review-page"
      className="flex h-full min-h-0 w-full flex-col gap-6 px-[var(--gutter)] py-6"
    >
      <RecordHeader
        title={review.name}
        breadcrumb={[
          { label: t("settings.index.title"), to: SETTINGS_PATH },
          { label: t("access.reviews.title"), to: ACCESS_REVIEWS_ROUTE },
        ]}
        chips={chip === null ? null : <StatusChip status={chip.status} />}
        meta={[
          { label: t("access.review.asOf"), value: formatTimestamp(review.as_of) },
          {
            label: t("access.review.reviewers"),
            value:
              review.reviewers.length === 0
                ? NO_VALUE
                : review.reviewers.map((reviewer) => reviewer.display_name).join(", "),
          },
        ]}
        actions={actions}
        primaryAction={complete ?? undefined}
        banner={
          pendingNotice && review.counts.pending > 0 ? (
            <div data-testid="SF-14-banner-pending-items">
              <Banner
                tone="warning"
                title={t("access.review.pendingItems", {
                  count: review.counts.pending,
                  formatted: count(review.counts.pending),
                })}
              />
            </div>
          ) : undefined
        }
        kpis={
          <KpiStrip
            region
            testId="SF-14-kpi-strip"
            heading={t("access.review.kpi.heading")}
            kpis={[
              {
                id: "members",
                label: t("access.review.kpi.members"),
                value: String(review.counts.members),
                currency: "",
                kind: "count",
              },
              {
                id: "certified",
                label: t("access.review.kpi.certified"),
                value: String(review.counts.certified),
                currency: "",
                kind: "count",
              },
              {
                id: "revoke-requested",
                label: t("access.review.kpi.revokeRequested"),
                value: String(review.counts.revoke_requested),
                currency: "",
                kind: "count",
              },
              {
                id: "revoked",
                label: t("access.review.kpi.revoked"),
                value: String(review.counts.revoked),
                currency: "",
                kind: "count",
              },
              {
                id: "pending",
                label: t("access.review.kpi.pending"),
                value: String(review.counts.pending),
                currency: "",
                kind: "count",
              },
            ]}
          />
        }
      />
      <ItemsGrid
        me={me}
        review={review}
        canDecide={inReview}
        onRequestRevocation={(item) => setDialog({ kind: "revoke", item })}
        onConfirmRevocation={(item) => setDialog({ kind: "confirm-revocation", item })}
      />
      {dialog.kind === "action" ? (
        <ReviewActionDialog review={review} action={dialog.action} onClose={close} />
      ) : null}
      {dialog.kind === "revoke" ? (
        <RequestRevocationDialog review={review} item={dialog.item} onClose={close} />
      ) : null}
      {dialog.kind === "confirm-revocation" ? (
        <ConfirmRevocationDialog review={review} item={dialog.item} onClose={close} />
      ) : null}
    </div>
  );
}

interface ItemsGridProps {
  readonly me: Me;
  readonly review: AccessReview;
  readonly canDecide: boolean;
  readonly onRequestRevocation: (item: AccessReviewItem) => void;
  readonly onConfirmRevocation: (item: AccessReviewItem) => void;
}

/** SCREENS_B §9.13 items grid; decisions render only while the campaign is in review. */
function ItemsGrid({
  me,
  review,
  canDecide,
  onRequestRevocation,
  onConfirmRevocation,
}: ItemsGridProps) {
  const own = me.active_membership_id;
  const allEntities = t("access.users.scope.all");
  const columns = useMemo<readonly GridColumn<AccessReviewItem>[]>(
    () => [
      {
        id: "member",
        header: t("access.review.column.member"),
        kind: "identifier",
        value: (item) => item.display_name,
        render: (item) => (
          <span className="flex flex-col">
            <span>{item.display_name}</span>
            <span className="font-mono text-mono text-fg-3">{item.user_email_snapshot}</span>
          </span>
        ),
        width: 224,
      },
      {
        id: "roles",
        header: t("access.review.column.roles"),
        kind: "text",
        value: (item) => rolesSnapshotText(item.roles_snapshot, allEntities),
        width: 360,
      },
      {
        id: "last_login_at",
        header: t("access.review.column.lastLogin"),
        kind: "timestamp",
        value: (item) => item.last_login_at,
        render: (item) =>
          item.last_login_at === null ? (
            <span className="text-fg-3">{t("access.users.lastLogin.never")}</span>
          ) : (
            <span className="num">{formatTimestamp(item.last_login_at)}</span>
          ),
      },
      {
        id: "granted",
        header: t("access.review.column.granted"),
        kind: "timestamp",
        value: (item) => earliestGrant(item.roles_snapshot),
      },
      {
        id: "granted_by",
        header: t("access.review.column.grantedBy"),
        kind: "text",
        value: (item) => grantors(item.roles_snapshot).join(", ") || null,
        width: 160,
      },
      {
        id: "decision",
        header: t("access.review.column.decision"),
        kind: "actions",
        value: (item) => item.decision,
        render: (item) => (
          <span className="flex flex-wrap items-center gap-2">
            {item.decision === "PENDING" ? null : (
              <StatusChip status={decisionChip(item.decision)} />
            )}
            {canDecide && item.membership_id === own && item.decision === "PENDING" ? (
              <span className="text-body-sm text-fg-3">{t("access.review.ownRow")}</span>
            ) : null}
            {canDecide && item.membership_id !== own && item.decision === "PENDING" ? (
              <>
                <CertifyButton review={review} item={item} />
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={t("access.review.requestRevocationFor", {
                    member: item.display_name,
                  })}
                  onClick={() => onRequestRevocation(item)}
                >
                  {t("access.review.requestRevocation")}
                </Button>
              </>
            ) : null}
            {canDecide && item.decision === "REVOKE_REQUESTED" ? (
              <Button variant="secondary" size="sm" onClick={() => onConfirmRevocation(item)}>
                {t("access.review.confirmRevocation")}
              </Button>
            ) : null}
          </span>
        ),
        width: 360,
      },
    ],
    [allEntities, canDecide, onConfirmRevocation, onRequestRevocation, own, review],
  );
  const source: GridSource<AccessReviewItem> = {
    queryKey: reviewItemsKey(review.id),
    fetchPage: (cursor, sort) => fetchReviewItemsPage(review.id, cursor, sort),
  };
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <DataGrid<AccessReviewItem>
        name="access-review-items"
        title={t("access.review.grid")}
        errorTitle={t("access.review.loadItemsError")}
        countLabel={(value, formatted) => t("access.review.itemCount", { count: value, formatted })}
        columns={columns}
        source={source}
        rowKey={(item) => item.id}
        rowLabel={(item) => item.display_name}
        testIdPrefix="SF-14"
        rowTestKey={(item) => item.user_email_snapshot}
        emptyState={
          <EmptyState
            title={t("access.review.empty.title")}
            description={t("access.review.empty.description")}
          />
        }
      />
    </div>
  );
}

/** "Certify <member>": one command per row, so each decision keeps its own Idempotency-Key. */
function CertifyButton({
  review,
  item,
}: {
  readonly review: AccessReview;
  readonly item: AccessReviewItem;
}) {
  const toast = useToast();
  const decide = useCommand<AccessReviewItem>({
    method: "POST",
    path: itemDecidePath(review.id, item.id),
    invalidates: [reviewItemsKey(review.id), reviewKey(review.id), EVERY_ACCESS_REVIEW],
  });
  return (
    <Button
      variant="secondary"
      size="sm"
      loading={decide.pending}
      aria-label={t("access.review.certifyMember", { member: item.display_name })}
      onClick={() => {
        void (async () => {
          const body: AccessReviewDecide = { decision: "CERTIFIED" };
          const outcome = await decide.submit(body);
          if (outcome.kind === "succeeded") {
            toast.show({
              tone: "positive",
              message: t("access.review.toast.certified", { member: item.display_name }),
            });
          } else if (outcome.kind === "failed") {
            toast.show({
              tone: "negative",
              message: outcome.problem.detail ?? outcome.problem.title,
            });
          }
        })();
      }}
    >
      {t("access.review.certify")}
    </Button>
  );
}

interface ReviewActionDialogProps {
  readonly review: AccessReview;
  readonly action: ReviewAction;
  readonly onClose: () => void;
}

function ReviewActionDialog({ review, action, onClose }: ReviewActionDialogProps) {
  const toast = useToast();
  const command = useCommand<AccessReview>({
    method: "POST",
    path: reviewActionPath(review.id, action),
    invalidates: [reviewKey(review.id), reviewItemsKey(review.id), EVERY_ACCESS_REVIEW],
  });
  const params = { name: review.name };
  const copy = {
    start: {
      title: t("access.review.startDialog.title", params),
      description: t("access.review.startDialog.description"),
      confirm: t("access.review.startDialog.confirm"),
      toast: t("access.review.toast.started", params),
      destructive: false,
    },
    complete: {
      title: t("access.review.completeDialog.title", params),
      description: t("access.review.completeDialog.description"),
      confirm: t("access.review.completeDialog.confirm"),
      toast: t("access.review.toast.completed", params),
      destructive: false,
    },
    cancel: {
      title: t("access.review.cancelDialog.title", params),
      description: t("access.review.cancelDialog.description"),
      confirm: t("access.review.cancelDialog.confirm"),
      toast: t("access.review.toast.cancelled", params),
      destructive: true,
    },
  }[action];
  return (
    <Modal
      open
      variant="confirmation"
      title={copy.title}
      description={copy.description}
      primaryAction={{
        label: copy.confirm,
        destructive: copy.destructive,
        onAction: () => {
          void (async () => {
            const outcome = await command.submit();
            if (outcome.kind === "succeeded") {
              toast.show({ tone: "positive", message: copy.toast });
              onClose();
            }
          })();
        },
      }}
      submitting={command.pending}
      onClose={onClose}
      testId={`SF-14-dialog-review-${action}`}
    >
      <RefusalBanner problem={command.problem} />
    </Modal>
  );
}

interface ItemDialogProps {
  readonly review: AccessReview;
  readonly item: AccessReviewItem;
  readonly onClose: () => void;
}

/** SCREENS_B §9.13 "Request revocation": a comment of at least 10 characters. */
function RequestRevocationDialog({ review, item, onClose }: ItemDialogProps) {
  const formId = useId();
  const toast = useToast();
  const [comment, setComment] = useState("");
  const [attempted, setAttempted] = useState(false);
  const decide = useCommand<AccessReviewItem>({
    method: "POST",
    path: itemDecidePath(review.id, item.id),
    invalidates: [reviewItemsKey(review.id), reviewKey(review.id), EVERY_ACCESS_REVIEW],
  });
  const submit = async () => {
    setAttempted(true);
    if (reasonError(comment) !== null) {
      return;
    }
    const body: AccessReviewDecide = { decision: "REVOKE_REQUESTED", comment: comment.trim() };
    const outcome = await decide.submit(body);
    if (outcome.kind === "succeeded") {
      toast.show({
        tone: "positive",
        message: t("access.review.toast.revocationRequested", { member: item.display_name }),
      });
      onClose();
    }
  };
  return (
    <Modal
      open
      variant="form"
      title={t("access.review.revokeDialog.title", { member: item.display_name })}
      description={t("access.review.revokeDialog.description")}
      primaryAction={{
        label: t("access.review.revokeDialog.confirm"),
        destructive: true,
        form: formId,
      }}
      submitting={decide.pending}
      onClose={onClose}
      testId="SF-14-dialog-request-revocation"
    >
      <form
        id={formId}
        noValidate
        className="flex flex-col gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <RefusalBanner problem={decide.problem} />
        <ReasonField
          name="revocation_comment"
          label={t("access.review.revokeDialog.comment")}
          value={comment}
          onChange={setComment}
          showError={attempted}
        />
      </form>
    </Modal>
  );
}

/** SCREENS_B §9.13 "Confirm revocation" records the completion of a requested revocation. */
function ConfirmRevocationDialog({ review, item, onClose }: ItemDialogProps) {
  const toast = useToast();
  const confirm = useCommand<AccessReviewItem>({
    method: "POST",
    path: itemConfirmRevocationPath(review.id, item.id),
    invalidates: [reviewItemsKey(review.id), reviewKey(review.id), EVERY_ACCESS_REVIEW],
  });
  return (
    <Modal
      open
      variant="confirmation"
      title={t("access.review.confirmDialog.title", { member: item.display_name })}
      description={t("access.review.confirmDialog.description")}
      primaryAction={{
        label: t("access.review.confirmDialog.confirm"),
        onAction: () => {
          void (async () => {
            const outcome = await confirm.submit();
            if (outcome.kind === "succeeded") {
              toast.show({
                tone: "positive",
                message: t("access.review.toast.revocationConfirmed", {
                  member: item.display_name,
                }),
              });
              onClose();
            }
          })();
        },
      }}
      submitting={confirm.pending}
      onClose={onClose}
      testId="SF-14-dialog-confirm-revocation"
    >
      <RefusalBanner problem={confirm.problem} />
    </Modal>
  );
}
