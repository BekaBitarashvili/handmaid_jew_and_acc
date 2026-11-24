"""HTML sanitising for rich-text fields (owner-edited descriptions and stories)."""

import nh3

ALLOWED_TAGS = {"p", "br", "strong", "em", "a", "ul", "ol", "li", "h3"}
ALLOWED_ATTRIBUTES = {"a": {"href"}}
ALLOWED_URL_SCHEMES = {"http", "https", "mailto", "tel"}

# The editor (Trix) emits <div>, <b>, <i>, <h1>; map them to the allowed set first.
_REWRITES = (
    ("<div>", "<p>"),
    ("</div>", "</p>"),
    ("<b>", "<strong>"),
    ("</b>", "</strong>"),
    ("<i>", "<em>"),
    ("</i>", "</em>"),
    ("<h1>", "<h3>"),
    ("</h1>", "</h3>"),
    ("<h2>", "<h3>"),
    ("</h2>", "</h3>"),
)


def clean_html(value: str | None) -> str:
    """Return safe HTML limited to p, br, strong, em, a, ul, ol, li, h3."""
    if not value:
        return ""
    for old, new in _REWRITES:
        value = value.replace(old, new)
    cleaned = nh3.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel="noopener noreferrer",
    )
    return cleaned.replace("<p></p>", "").strip()
