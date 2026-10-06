"""What stands for a request's content where a reader is not shown it, as pure functions (04
§16.10 rev 1.208 "Content of a request"; dev-guide DG-KRN-APR-10; item APR-CONTENT-SCOPE-1, the
supervisor's ruling of 2026-10-01 on the security review's finding of a reader who covers one of
a request's entities).

(a) every subject type has a name, the words the web shows for it; (b) the summary such a reader
is shown names the type and the request and nothing of the record; (c) the list of requests
reads no content column but through the reader's own key. The database-bound witnesses — who is
shown the content, the file and attachment routes, the notifications — are
``tests/domain/platform/test_approval_scope.py``, ``tests/api/test_approvals_api.py`` and
``tests/domain/imports/test_entity_scope.py``.
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from erev_api.api.v1 import approvals as route
from erev_api.approvals import subjects
from erev_api.controls.registry import REPOSITORY_ROOT
from erev_api.db.tables import approval_request
from erev_api.domain.platform import approval_queries
from erev_api.enums import ApprovalSubjectType

MESSAGES = REPOSITORY_ROOT / "frontend" / "src" / "messages" / "en.json"


def test_every_subject_type_has_the_name_the_web_shows() -> None:
    """A request whose content is withheld is summarised by its type's name, so every value of
    E-08 has one — a type whose phase is not built too: the lookup must not fail for a row that
    exists — and it is the web's ``approvals.subjectType.<literal>`` message, word for word
    (SCREENS §15.3 "Subject type labels"). A value added to E-08 fails here until the server
    and the web name it alike."""
    assert set(subjects.SUBJECT_LABELS) == set(ApprovalSubjectType)
    messages = json.loads(MESSAGES.read_text(encoding="utf-8"))
    web = {
        subject_type: messages.get(f"approvals.subjectType.{subject_type.value}")
        for subject_type in ApprovalSubjectType
    }
    assert dict(subjects.SUBJECT_LABELS) == web
    assert subjects.SUBJECT_LABELS[ApprovalSubjectType.MIGRATION_SSP_REPLAY] == (
        "Migration SSP replay"
    )


def test_the_withheld_summary_names_the_type_and_the_request_only() -> None:
    assert (
        subjects.withheld_summary(ApprovalSubjectType.IMPORT_COMMIT, "APR-000007")
        == "Import commit APR-000007"
    )
    assert subjects.withheld_summary("ROLE_ASSIGNMENT", "APR-000012") == (
        "Role assignment APR-000012"
    )


def _name(column: sa.ColumnElement[object]) -> str:
    element = column.element if isinstance(column, sa.Label) else column
    assert isinstance(element, sa.Column), column
    assert element.table is approval_request, column
    return str(element.name)


def test_the_list_reads_no_content_column_but_through_the_readers_own_key() -> None:
    """A filter, a search column or a sort key on a member a row withholds would tell it: a
    search finds the row by a contract's name, a range brackets its amount, an order ranks it.
    The catalogue names one such key, ``amount``; the route replaces its column by the reader's
    own (``approval_list``), and nothing else of the catalogue is a content column. Whoever adds
    a filter or a search column on one meets this test, and ``approval_queries.shown``."""
    spec = route.APPROVAL_LIST
    content = approval_queries.CONTENT_COLUMNS
    assert content <= {column.name for column in approval_request.c}
    assert {name for name, key in spec.sort_keys.items() if _name(key) in content} == {"amount"}
    assert [item.name for item in spec.filters.values() if _name(item.column) in content] == []
    assert spec.search_columns == ()

    own = sa.literal_column("own_amount")
    reader = route.approval_list(own)
    assert reader.sort_keys["amount"] is own
    assert {name: key for name, key in reader.sort_keys.items() if name != "amount"} == {
        name: key for name, key in spec.sort_keys.items() if name != "amount"
    }
    assert (reader.resource, reader.filters, reader.directions, reader.custom_filters) == (
        spec.resource,
        spec.filters,
        spec.directions,
        spec.custom_filters,
    )
