"""PDF export of the same verified disclosure chapters used by the workbook."""

from collections.abc import Mapping
from uuid import UUID

from erev_api.domain.reports.disclosure_assembly import Pack
from erev_api.domain.reports.disclosure_workbook import chapters
from erev_api.domain.reports.outputs import RunStamp
from erev_api.domain.reports.outputs.pdf import render_pdf_chapters


def render(pack: Pack, stamp: RunStamp, child_stamps: Mapping[UUID, RunStamp]) -> bytes:
    """Verify original child outputs and policies before rendering any disclosure amounts."""
    return render_pdf_chapters(chapters(pack, stamp, child_stamps), stamp)
