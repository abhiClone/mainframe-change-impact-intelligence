"""Phase 3A API router: deterministic change-set & release analysis.

Additive layer: no existing endpoint is modified.

  POST /api/change-set/analyze -> ChangeSetIntelligence

The request carries already-supplied changed-file metadata only; the
server analyzes its own fixed sample_mainframe tree. Arbitrary
filesystem/Git repository paths are NOT accepted here (local Git diff
mode lives in the CLI/service layer), so this endpoint cannot become
an arbitrary filesystem reader.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.changeset import (
    ChangeSetAnalyzer,
    ExplicitFileListProvider,
    build_view,
)
from backend.changeset.ai import get_change_set_explainer
from backend.changeset.models import (
    ChangedFile,
    ChangeSetIntelligence,
    ChangeStatus,
)

router = APIRouter()

REPO_DIR = Path(__file__).resolve().parents[2] / "sample_mainframe"

_ANALYZER: ChangeSetAnalyzer | None = None


def _analyzer() -> ChangeSetAnalyzer:
    """Process-wide analyzer over the server's fixed Mainframe tree."""
    global _ANALYZER
    if _ANALYZER is None:
        _ANALYZER = ChangeSetAnalyzer(build_view(REPO_DIR))
    return _ANALYZER


class ChangeSetFileInput(BaseModel):
    path: str = Field(
        ..., description="Repo-relative path, e.g. 'copybook/WARRCOPY.cpy'."
    )
    status: ChangeStatus = Field(default="modified")


class ChangeSetAnalyzeRequest(BaseModel):
    files: list[ChangeSetFileInput] = Field(
        ..., description="Changed files (explicit file-list provider input)."
    )
    resolutions: dict[str, list[str]] | None = Field(
        default=None,
        description=(
            "Explicit ambiguity resolutions: file path -> selected "
            "component ids (each must be a valid candidate)."
        ),
    )


@router.post(
    "/api/change-set/analyze",
    response_model=ChangeSetIntelligence,
    summary="Deterministic change-set & release-candidate analysis",
)
def analyze_change_set(request: ChangeSetAnalyzeRequest) -> ChangeSetIntelligence:
    provider = ExplicitFileListProvider(
        [
            ChangedFile(path=f.path, status=f.status)
            for f in request.files
        ]
    )
    analyzer = _analyzer()
    try:
        return analyzer.analyze(
            provider.get_changes(),
            resolutions=request.resolutions or {},
            provider=provider,
            explainer=get_change_set_explainer(),
        )
    except ValueError as exc:
        # Invalid ambiguity resolution (or other deterministic input error).
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        # Invalid backend data (catalog/dataset) — fail clearly, 500.
        raise HTTPException(status_code=500, detail=str(exc))
