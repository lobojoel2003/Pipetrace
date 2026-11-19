"""Template helpers shared by resident and staff pages."""

from __future__ import annotations

from django import template
from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils import translation
from django.utils.html import format_html, json_script
from django.utils.safestring import mark_safe

register = template.Library()

#: Map/legend marker shapes per status code. Shape is a second cue next to colour.
SHAPES = {
    "L": '<circle cx="8" cy="8" r="6.5"/>',
    "G": '<path d="M8 1.2 14.8 8 8 14.8 1.2 8Z"/>',
    "U": '<rect x="2" y="2" width="12" height="12" rx="2.5"/>',
    "N": '<circle cx="8" cy="8" r="4.75"/>',
}
CODE_CLASS = {"L": "lead", "G": "grr", "U": "unknown", "N": "nonlead"}
STATUS_CODE = {"lead": "L", "grr": "G", "unknown": "U", "non_lead": "N"}


@register.simple_tag
def status_shape(code: str, size: int = 16, label: str = ""):
    """An inline SVG marker matching the map symbol for a status."""
    code = STATUS_CODE.get(code, code)
    shape = SHAPES.get(code, SHAPES["U"])
    aria = format_html('role="img" aria-label="{}"', label) if label else 'aria-hidden="true"'
    return mark_safe(
        f'<svg class="shape shape-{CODE_CLASS.get(code, "unknown")}" width="{size}" '
        f'height="{size}" viewBox="0 0 16 16" {aria} focusable="false">{shape}</svg>'
    )


@register.filter
def status_class(status: str) -> str:
    return CODE_CLASS.get(STATUS_CODE.get(status, status), "unknown")


@register.simple_tag(takes_context=True)
def alternate_url(context, language: str) -> str:
    """The current page in another language (works in the static export too)."""
    request = context.get("request")
    match = getattr(request, "resolver_match", None) if request else None
    query = ""
    if request is not None and request.GET and not getattr(request, "static_export", False):
        query = "?" + request.GET.urlencode()
    if match and match.view_name:
        with translation.override(language):
            try:
                return reverse(match.view_name, args=match.args, kwargs=match.kwargs) + query
            except NoReverseMatch:
                pass
    with translation.override(language):
        return reverse("residents:home")


@register.simple_tag
def other_languages():
    current = (translation.get_language() or "en")[:2]
    return [(code, name) for code, name in settings.LANGUAGES if code != current]


@register.simple_tag(takes_context=True)
def js_config(context):
    """Configuration for the site's JavaScript, as a JSON <script> block."""
    from pipetrace.residents.status import js_labels

    site = context["site"]
    static_mode = context.get("static_mode", False)
    data = {
        "lang": (translation.get_language() or "en")[:2],
        "static": bool(static_mode),
        "searchApi": reverse("api:search"),
        "searchIndex": reverse("api:search_index"),
        "searchPage": reverse("residents:search"),
        "lineUrl": reverse("residents:line", kwargs={"public_id": "__ID__"}),
        "submitUrl": site.static_form_endpoint if static_mode else "",
        "email": site.email,
        "phone": site.phone,
        "utility": site.display_name,
        "labels": js_labels(),
    }
    return json_script(data, "pipetrace-config")


@register.filter
def localized(site, field: str) -> str:
    return site.localized(field)


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None
