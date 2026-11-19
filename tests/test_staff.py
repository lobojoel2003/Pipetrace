import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile

from pipetrace.inventory.choices import Material, Status
from pipetrace.inventory.models import ImportBatch, ServiceLine
from pipetrace.residents.models import InspectionRequest, PipeCheck

from .conftest import xlsx_bytes

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff(client, site):
    user = User.objects.create_user("clerk", password="pw-test-12345", is_staff=True)
    client.force_login(user)
    return client


def test_staff_requires_login(client, site):
    response = client.get("/staff/")
    assert response.status_code == 302
    assert response.url.startswith("/staff/login/")
    user = User.objects.create_user("resident", password="pw-test-12345")
    client.force_login(user)
    assert client.get("/staff/").status_code == 302  # not staff


def test_login_page(client, site):
    assert client.get("/staff/login/").status_code == 200


def test_import_wizard_end_to_end(staff, epa_rows):
    upload = SimpleUploadedFile("inventory.xlsx", xlsx_bytes(epa_rows).getvalue())
    response = staff.post("/staff/imports/new/", {"file": upload, "mode": "merge"})
    batch = ImportBatch.objects.get()
    assert response.url == f"/staff/imports/{batch.pk}/columns/"
    assert batch.header_row == 4
    assert batch.column_map["address"] == 1

    page = staff.get(response.url)
    assert page.status_code == 200
    assert "System-Owned Portion › Material" in page.content.decode()

    # Change the header row, then put it back.
    assert staff.get(f"{response.url}?header_row=1").status_code == 200
    staff.get(f"{response.url}?header_row=4")
    batch.refresh_from_db()
    form = {f"map_{k}": str(v) for k, v in batch.column_map.items()}
    response = staff.post(f"/staff/imports/{batch.pk}/columns/", form)
    assert response.url == f"/staff/imports/{batch.pk}/values/"

    values = staff.get(response.url)
    assert values.status_code == 200
    response = staff.post(response.url, {"value_system_material_cu": Material.PLASTIC})
    assert response.url == f"/staff/imports/{batch.pk}/preview/"
    batch.refresh_from_db()
    assert batch.value_map == {"system_material": {"cu": Material.PLASTIC}}

    preview = staff.get(response.url)
    assert preview.status_code == 200
    assert "Import 4 lines" in preview.content.decode()
    response = staff.post(response.url, {"mode": "merge"})
    assert response.url.startswith("/staff/geocode/")
    batch.refresh_from_db()
    assert batch.state == ImportBatch.State.COMMITTED
    assert batch.stats["created"] == 4
    assert ServiceLine.objects.get(source_id="T-2").system_material == Material.PLASTIC
    assert staff.get(batch.get_absolute_url()).status_code == 200
    assert staff.get(response.url).status_code == 200

    # A second upload of the same layout reuses the mapping and value choices.
    upload = SimpleUploadedFile("inventory-v2.xlsx", xlsx_bytes(epa_rows).getvalue())
    staff.post("/staff/imports/new/", {"file": upload, "mode": "merge"})
    second = ImportBatch.objects.order_by("-pk").first()
    assert second.column_map == batch.column_map
    assert second.value_map == batch.value_map


def test_mapping_validation_errors(staff, epa_rows):
    upload = SimpleUploadedFile("inventory.xlsx", xlsx_bytes(epa_rows).getvalue())
    staff.post("/staff/imports/new/", {"file": upload, "mode": "merge"})
    batch = ImportBatch.objects.get()
    response = staff.post(f"/staff/imports/{batch.pk}/columns/", {"map_city": "2"})
    assert response.status_code == 200
    assert "street address" in response.content.decode()


def test_upload_rejects_bad_files(staff):
    upload = SimpleUploadedFile("old.xls", b"\xd0\xcf\x11\xe0")
    response = staff.post("/staff/imports/new/", {"file": upload, "mode": "merge"})
    assert "Old .xls files" in response.content.decode()
    upload = SimpleUploadedFile("broken.xlsx", b"PK\x03\x04garbage")
    response = staff.post("/staff/imports/new/", {"file": upload, "mode": "merge"})
    assert "Could not open" in response.content.decode()
    assert ImportBatch.objects.count() == 0


def test_staff_pages(staff, lines):
    for path in [
        "/staff/",
        "/staff/imports/",
        "/staff/lines/",
        "/staff/lines/?status=lead&q=12",
        "/staff/geocode/",
        "/staff/requests/",
        "/staff/photos/",
    ]:
        assert staff.get(path).status_code == 200, path
    csv = staff.get("/staff/export/inventory.csv")
    assert csv["Content-Type"].startswith("text/csv")
    text = csv.content.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("Service Line ID,Street Address")
    assert "12 Maple St" in text
    assert staff.get("/staff/settings/").status_code == 302


def test_geocode_step_endpoint(staff, lines):
    response = staff.post("/staff/geocode/step/")
    assert response.status_code == 502  # geocoding is off in tests
    assert "turned off" in response.json()["error"]
    assert staff.post("/staff/geocode/retry/").status_code == 302


def test_request_update(staff, lines):
    item = InspectionRequest.objects.create(address="12 Maple St", phone="555")
    response = staff.post(
        f"/staff/requests/{item.pk}/", {"state": "scheduled", "staff_notes": "Tue 9am"}
    )
    assert response.status_code == 302
    item.refresh_from_db()
    assert item.state == "scheduled"


def test_photo_review_updates_inventory(staff, lines):
    from pipetrace.inventory.management.commands.load_demo import demo_photo

    check = PipeCheck(address="16 Maple St", service_line=lines["unknown"], scratch="silver")
    check.photo.save("p.jpg", demo_photo(), save=False)
    check.save()
    assert staff.get(f"/staff/photos/{check.pk}/").status_code == 200
    image = staff.get(f"/staff/photos/{check.pk}/image/1/")
    assert image["Content-Type"] == "image/jpeg"
    assert staff.get(f"/staff/photos/{check.pk}/image/2/").status_code == 404
    response = staff.post(
        f"/staff/photos/{check.pk}/",
        {"state": "reviewed", "staff_material": "lead", "apply": "on", "staff_notes": ""},
    )
    assert response.status_code == 302
    line = ServiceLine.objects.get(pk=lines["unknown"].pk)
    assert line.customer_material == Material.LEAD
    assert line.status == Status.LEAD
    assert "PC-" in line.basis
    check.refresh_from_db()
    assert check.applied_to_line
    assert check.reviewed_by.username == "clerk"


def test_admin_edits_location(staff, lines):
    admin = User.objects.create_superuser("boss", password="pw-test-12345")
    staff.force_login(admin)
    line = lines["unknown"]
    url = f"/admin/inventory/serviceline/{line.pk}/change/"
    page = staff.get(url)
    assert page.status_code == 200
    form = page.context["adminform"].form
    data = {k: v for k, v in form.initial.items() if v is not None and not isinstance(v, dict)}
    data.update(
        {
            "address": line.address,
            "latitude": "40.25",
            "longitude": "-89.25",
            "extra": "{}",
            "system_material": "copper",
            "customer_material": "copper",
            "replacement": "not_scheduled",
            "geocode_status": "provided",
            "status": "unknown",
            "active": "on",
        }
    )
    response = staff.post(url, data)
    assert response.status_code == 302, response.context["adminform"].form.errors
    line.refresh_from_db()
    assert line.geocode_status == "manual"
    assert round(line.location.y, 2) == 40.25
    assert line.status == Status.NON_LEAD  # materials changed, status recomputed
