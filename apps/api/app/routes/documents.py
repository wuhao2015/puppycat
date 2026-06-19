from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.deps import get_current_user
from app.documents import (
    render_cover_letter_pdf,
    render_itinerary_pdf,
    render_visa_pdf,
)
from app.schemas import CoverLetterRequest, Itinerary, VisaChecklist

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _pdf_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/itinerary", dependencies=[Depends(get_current_user)])
async def itinerary_pdf(itinerary: Itinerary) -> Response:
    pdf = render_itinerary_pdf(itinerary)
    name = f"itinerary-{itinerary.destination.lower().replace(' ', '-')}.pdf"
    return _pdf_response(pdf, name)


@router.post("/visa", dependencies=[Depends(get_current_user)])
async def visa_pdf(checklist: VisaChecklist) -> Response:
    pdf = render_visa_pdf(checklist)
    return _pdf_response(pdf, "visa-checklist.pdf")


@router.post("/cover-letter", dependencies=[Depends(get_current_user)])
async def cover_letter_pdf(req: CoverLetterRequest) -> Response:
    pdf = render_cover_letter_pdf(req)
    return _pdf_response(pdf, "visa-cover-letter.pdf")
