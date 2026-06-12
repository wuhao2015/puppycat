from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.schemas import CoverLetterRequest, Itinerary, VisaChecklist

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


@lru_cache
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )


@lru_cache
def _css() -> str:
    return (_TEMPLATE_DIR / "base.css").read_text()


def _render_pdf(template_name: str, **context) -> bytes:
    # Imported lazily so importing this module does not require the native
    # WeasyPrint libraries (useful for tests / environments without them).
    from weasyprint import HTML

    html = _env().get_template(template_name).render(css=_css(), **context)
    return HTML(string=html).write_pdf()


def render_itinerary_pdf(itinerary: Itinerary) -> bytes:
    return _render_pdf("itinerary.html", itinerary=itinerary)


def render_visa_pdf(checklist: VisaChecklist) -> bytes:
    return _render_pdf("visa.html", checklist=checklist)


def render_cover_letter_pdf(req: CoverLetterRequest) -> bytes:
    return _render_pdf("cover_letter.html", req=req, today=date.today().isoformat())
