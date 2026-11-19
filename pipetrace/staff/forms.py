from __future__ import annotations

from pathlib import Path

from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from pipetrace.inventory.choices import Material
from pipetrace.inventory.importer.readers import SUPPORTED_EXTENSIONS
from pipetrace.inventory.models import ImportBatch
from pipetrace.residents.models import InspectionRequest, PipeCheck


class UploadForm(forms.Form):
    file = forms.FileField(
        label=_("Inventory spreadsheet"),
        help_text=_("Excel (.xlsx) or CSV. The EPA inventory template works as is."),
        widget=forms.ClearableFileInput(attrs={"accept": ".xlsx,.xlsm,.csv,.tsv,.txt"}),
    )
    mode = forms.ChoiceField(
        label=_("What should this file do?"),
        choices=ImportBatch.Mode.choices,
        initial=ImportBatch.Mode.MERGE,
        widget=forms.RadioSelect,
    )

    def clean_file(self):
        upload = self.cleaned_data["file"]
        ext = Path(upload.name).suffix.lower()
        if ext == ".xls":
            raise forms.ValidationError(
                _(
                    "Old .xls files can't be read. Save the file as .xlsx "
                    "or .csv and upload it again."
                )
            )
        if ext not in SUPPORTED_EXTENSIONS:
            raise forms.ValidationError(_("Upload an .xlsx or .csv file."))
        limit = settings.PIPETRACE["MAX_IMPORT_MB"]
        if upload.size > limit * 1024 * 1024:
            raise forms.ValidationError(_("Files must be smaller than %(mb)s MB.") % {"mb": limit})
        return upload


class InspectionUpdateForm(forms.ModelForm):
    class Meta:
        model = InspectionRequest
        fields = ["state", "staff_notes"]
        widgets = {"staff_notes": forms.Textarea(attrs={"rows": 4})}


class PhotoReviewForm(forms.ModelForm):
    apply = forms.BooleanField(
        label=_("Update the inventory: set the customer-side material for this line"),
        required=False,
    )

    class Meta:
        model = PipeCheck
        fields = ["state", "staff_material", "staff_notes"]
        widgets = {"staff_notes": forms.Textarea(attrs={"rows": 3})}
        labels = {"staff_material": _("What the photo shows")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["staff_material"].choices = [("", "—")] + [
            c for c in Material.choices if c[0] != Material.NON_LEAD
        ]

    def clean(self):
        data = super().clean()
        if data.get("apply") and not data.get("staff_material"):
            raise forms.ValidationError(_("Choose the material before updating the inventory."))
        if data.get("apply") and not self.instance.service_line_id:
            raise forms.ValidationError(_("This photo isn't linked to a line in the inventory."))
        return data
