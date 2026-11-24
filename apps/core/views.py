from django.conf import settings
from django.db import connection
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .design_tokens import DECORATIVE, SURFACES, TEXT, color_tokens, contrast

GEORGIAN_SAMPLE = "ხელნაკეთი სამკაულები ბუნებრივი ქვებით"
LATIN_SAMPLE = "Handmade jewelry with natural stones"


@never_cache
@require_GET
def healthz(request: HttpRequest) -> JsonResponse:
    """Liveness + database check for container healthchecks and uptime monitors."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "error", "database": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


def _static_redirect(path: str):
    """Browsers and iOS request some icons at the site root; point them at static files.

    Temporary (302) redirect, cached for a day: the hashed static URL changes when
    the icon is replaced, so a permanent redirect would pin the old file.
    """

    @require_GET
    def view(request: HttpRequest) -> HttpResponse:
        response = redirect(static(path))
        response["Cache-Control"] = "public, max-age=86400"
        return response

    return view


favicon_ico = _static_redirect("brand/favicon.ico")
apple_touch_icon = _static_redirect("brand/apple-touch-icon.png")


def _swatches(names: tuple[str, ...]) -> list[dict]:
    tokens = color_tokens()
    ivory, cream = tokens["ivory"].hex, tokens["cream"].hex
    return [
        {
            "token": tokens[name],
            "on_ivory": contrast(tokens[name].hex, ivory),
            "on_cream": contrast(tokens[name].hex, cream),
        }
        for name in names
    ]


@require_GET
def styleguide(request: HttpRequest) -> HttpResponse:
    """Design-system reference for checking fonts, tokens and components (DEBUG only)."""
    if not settings.DEBUG:
        raise Http404
    context = {
        "georgian_sample": GEORGIAN_SAMPLE,
        "latin_sample": LATIN_SAMPLE,
        "surfaces": _swatches(SURFACES),
        "text_colors": _swatches(TEXT),
        "decorative_colors": _swatches(DECORATIVE),
        "weights": (300, 400, 500),
        "type_scale": (
            ("display", "display", "48–88px"),
            ("h1", "text-h1", "36–56px"),
            ("h2", "text-h2", "28–40px"),
            ("h3", "text-h3", "20–26px"),
            ("body", "text-body", "16–17px"),
            ("small", "text-small", "13–14px"),
        ),
    }
    return render(request, "core/styleguide.html", context)
