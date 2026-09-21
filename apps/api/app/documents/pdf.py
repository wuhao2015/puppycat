from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import CSS, HTML

from app.schemas import Itinerary


_TEMPLATE_DIR = Path(__file__).parent / "templates"
_ENVIRONMENT = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(("html", "xml")),
)
_ITINERARY_TEMPLATE = _ENVIRONMENT.get_template("itinerary.html")
_BASE_STYLESHEET = CSS(filename=str(_TEMPLATE_DIR / "base.css"))


def render_itinerary_pdf(itinerary: Itinerary) -> bytes:
    html = _ITINERARY_TEMPLATE.render(
        itinerary=itinerary,
        weather_by_date={weather.date: weather for weather in itinerary.weather},
    )
    return HTML(string=html, base_url=str(_TEMPLATE_DIR)).write_pdf(
        stylesheets=[_BASE_STYLESHEET]
    )
