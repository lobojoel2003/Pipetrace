"""Forms residents fill in: request an inspection, send a photo of their pipe."""

from __future__ import annotations

import io
import secrets
import time

from django import forms
from django.conf import settings
from django.core import signing
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps, UnidentifiedImageError

from pipetrace.residents.models import InspectionRequest, PipeCheck, guess_material

MIN_SECONDS = 3  # faster than this is a bot
MAX_PHOTO_SIDE = 2400
_SIGNER_SALT = "pipetrace.form-started"


def started_token() -> str:
    return signing.dumps(time.time(), salt=_SIGNER_SALT)


class SpamProtectedForm(forms.Form):
    """Honeypot field plus a signed "form shown at" timestamp."""

    website = forms.CharField(
        required=False,
        label=_("Leave this field empty"),
        widget=forms.TextInput(attrs={"autocomplete": "off", "tabindex": "-1"}),
    )
    started = forms.CharField(required=False, widget=forms.HiddenInput)

    #: The static-site endpoint cannot hand out timestamps; it relies on the honeypot.
    require_started = True

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError(_("Please leave this field empty."))
        return ""

    def clean_started(self):
        token = self.cleaned_data.get("started")
        if not self.require_started:
            return token
        try:
            shown = signing.loads(token or "", salt=_SIGNER_SALT, max_age=60 * 60 * 24)
        except signing.BadSignature as exc:
            raise forms.ValidationError(
                _("This form expired. Please reload the page and try again.")
            ) from exc
        if time.time() - float(shown) < MIN_SECONDS:
            raise forms.ValidationError(
                _("That was quick! Please check the form and send it again.")
            )
        return token


class ContactMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["language"].required = False

    def clean_language(self):
        return self.cleaned_data.get("language") or "en"

    def clean(self):
        data = super().clean()
        if not data.get("phone") and not data.get("email"):
            raise forms.ValidationError(
                _("Please give us a phone number or an email address so we can reach you.")
            )
        return data


class InspectionRequestForm(ContactMixin, SpamProtectedForm, forms.ModelForm):
    consent = forms.BooleanField(
        label=_("The utility may contact me about this request."), required=True
    )

    class Meta:
        model = InspectionRequest
        fields = [
            "address",
            "name",
            "phone",
            "email",
            "contact_by",
            "best_time",
            "relationship",
            "message",
            "language",
        ]
        widgets = {
            "address": forms.TextInput(attrs={"autocomplete": "street-address"}),
            "name": forms.TextInput(attrs={"autocomplete": "name"}),
            "phone": forms.TextInput(
                attrs={"autocomplete": "tel", "type": "tel", "inputmode": "tel"}
            ),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "contact_by": forms.RadioSelect,
            "relationship": forms.RadioSelect,
            "message": forms.Textarea(attrs={"rows": 3}),
            "language": forms.HiddenInput,
        }
        labels = {
            "address": _("Address of the building"),
            "name": _("Your name"),
            "phone": _("Phone"),
            "email": _("Email"),
            "contact_by": _("How should we contact you?"),
            "best_time": _("Best days or times to reach you"),
            "relationship": _("Your connection to the property"),
            "message": _("Anything we should know? (optional)"),
        }
        help_texts = {
            "best_time": _("For example: weekday mornings."),
        }


class PipeCheckForm(ContactMixin, SpamProtectedForm, forms.ModelForm):
    class Meta:
        model = PipeCheck
        fields = [
            "address",
            "photo",
            "photo_2",
            "scratch",
            "magnet",
            "notes",
            "name",
            "phone",
            "email",
            "language",
        ]
        widgets = {
            "address": forms.TextInput(attrs={"autocomplete": "street-address"}),
            "photo": forms.ClearableFileInput(
                attrs={"accept": "image/*", "capture": "environment"}
            ),
            "photo_2": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "scratch": forms.RadioSelect,
            "magnet": forms.RadioSelect,
            "notes": forms.Textarea(attrs={"rows": 3}),
            "name": forms.TextInput(attrs={"autocomplete": "name"}),
            "phone": forms.TextInput(
                attrs={"autocomplete": "tel", "type": "tel", "inputmode": "tel"}
            ),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "language": forms.HiddenInput,
        }
        labels = {
            "address": _("Address of the building"),
            "photo": _("Photo of the scratched pipe"),
            "photo_2": _("Another photo (optional)"),
            "scratch": _("What did the scratch look like?"),
            "magnet": _("What happened with the magnet?"),
            "notes": _("Anything else? (optional)"),
            "name": _("Your name"),
            "phone": _("Phone"),
            "email": _("Email"),
        }
        help_texts = {
            "photo": _(
                "Take it close up, where the pipe comes through the wall or floor, "
                "with the scratched spot in focus."
            ),
        }

    def _clean_photo(self, name: str):
        upload = self.cleaned_data.get(name)
        if not upload:
            return upload
        limit = settings.PIPETRACE["MAX_PHOTO_MB"] * 1024 * 1024
        if upload.size > limit:
            raise forms.ValidationError(
                _("Photos must be smaller than %(mb)s MB.")
                % {"mb": settings.PIPETRACE["MAX_PHOTO_MB"]}
            )
        return clean_photo(upload)

    def clean_photo(self):
        return self._clean_photo("photo")

    def clean_photo_2(self):
        return self._clean_photo("photo_2")

    def save(self, commit=True):
        check = super().save(commit=False)
        check.resident_result = guess_material(check.scratch, check.magnet)
        if commit:
            check.save()
        return check


def clean_photo(upload):
    """Re-encode an uploaded photo as JPEG, upright, resized, without EXIF/GPS data."""
    try:
        upload.seek(0)
        with Image.open(upload) as image:
            image.load()
            image = ImageOps.exif_transpose(image)
            image.thumbnail((MAX_PHOTO_SIDE, MAX_PHOTO_SIDE))
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=85, optimize=True)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise forms.ValidationError(
            _("That file doesn't look like a photo. Please choose a JPEG or PNG image.")
        ) from exc
    out.seek(0)
    return InMemoryUploadedFile(
        out, "photo", f"{secrets.token_hex(12)}.jpg", "image/jpeg", out.getbuffer().nbytes, None
    )


class ApiInspectionRequestForm(InspectionRequestForm):
    require_started = False


class ApiPipeCheckForm(PipeCheckForm):
    require_started = False
