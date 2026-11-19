"""Plain-language wording for each classification, shared by pages, map and search."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from pipetrace.inventory.choices import STATUS_CODES, Status

STATUS_TEXT = {
    Status.LEAD: {
        "short": _("Lead"),
        "headline": _("This service line is made of lead."),
        "meaning": _(
            "Lead can dissolve into drinking water as it flows through the pipe. "
            "There is no known safe level of lead exposure, especially for children "
            "and during pregnancy."
        ),
    },
    Status.GRR: {
        "short": _("Galvanized, needs replacing"),
        "headline": _("This service line is galvanized steel that needs to be replaced."),
        "meaning": _(
            "Galvanized pipe that is, or ever was, connected after a lead pipe can "
            "collect lead inside it and release it into water later. Federal rules "
            "treat it like a lead line."
        ),
    },
    Status.UNKNOWN: {
        "short": _("Unknown"),
        "headline": _("We don't know yet what this service line is made of."),
        "meaning": _(
            "Our records don't show the pipe material. It could be lead. You can "
            "help us find out in about two minutes with a coin and a magnet."
        ),
    },
    Status.NON_LEAD: {
        "short": _("Not lead"),
        "headline": _("This service line is not made of lead."),
        "meaning": _(
            "Our records show that neither part of this service line is lead or "
            "galvanized pipe that needs replacing."
        ),
    },
}

#: Short label for a status code used in compact data files (L, G, U, N).
CODE_LABELS = {code: STATUS_TEXT[status]["short"] for status, code in STATUS_CODES.items()}


def status_text(status: str) -> dict:
    return {
        "code": STATUS_CODES[Status(status)],
        "status": status,
        **{k: str(v) for k, v in STATUS_TEXT[Status(status)].items()},
    }


def js_labels() -> dict:
    """Translated strings the browser needs (map popups, search results)."""
    return {
        "status": {code: str(label) for code, label in CODE_LABELS.items()},
        "replaced": str(_("Replaced")),
        "details": str(_("See details")),
        "noResults": str(
            _("No address found. Check the spelling, or try just the house number and street name.")
        ),
        "searching": str(_("Searching…")),
        "results": str(_("%(count)s addresses found")),
        "oneResult": str(_("1 address found")),
        "mapError": str(
            _("The map could not load. You can still search for your address or browse by street.")
        ),
        "legendShow": str(_("Show")),
        "sent": str(_("Thank you! Your reference number is")),
        "sendError": str(_("Sorry, that didn't go through. Please try again, or call us.")),
        "emailOpened": str(
            _("Your email app should open with your message. Attach your photo and press send.")
        ),
        "noEmail": str(_("This page can't send forms. Please call us instead.")),
        "sending": str(_("Sending…")),
        "demoMap": str(_("Fictional demo map")),
    }
