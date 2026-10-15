"""Retain extraction source/text references with immutable call intent."""

from erev_api.db import migration_ops as ops

revision = "0155"
down_revision = "0154"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.ai_call_intent ADD COLUMN file_object_id uuid, "
        "ADD COLUMN document_text_file_id uuid, "
        "ADD CONSTRAINT ck_ai_call_intent__documents "
        "CHECK ((file_object_id IS NULL) = (document_text_file_id IS NULL))"
    )
    ops.add_tenant_fk("ai_call_intent", "file_object_id", "file_object")
    ops.add_tenant_fk("ai_call_intent", "document_text_file_id", "file_object")


def downgrade() -> None:
    # Do not erase recovery/evidence bindings while their immutable intents survive.
    ops.execute(
        "ALTER TABLE erev.ai_call_intent ADD CONSTRAINT ck_ai_call_intent__0155_empty "
        "CHECK (document_text_file_id IS NULL) NOT VALID"
    )
    ops.execute("ALTER TABLE erev.ai_call_intent VALIDATE CONSTRAINT ck_ai_call_intent__0155_empty")
    ops.execute(
        "ALTER TABLE erev.ai_call_intent DROP CONSTRAINT ck_ai_call_intent__0155_empty, "
        "DROP COLUMN file_object_id, DROP COLUMN document_text_file_id"
    )
