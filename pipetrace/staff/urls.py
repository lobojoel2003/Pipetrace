from django.contrib.auth import views as auth_views
from django.urls import path

from pipetrace.staff import views

app_name = "staff"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("imports/", views.imports, name="imports"),
    path("imports/new/", views.import_upload, name="import_upload"),
    path("imports/<int:pk>/", views.import_detail, name="import_detail"),
    path("imports/<int:pk>/columns/", views.import_map, name="import_map"),
    path("imports/<int:pk>/values/", views.import_values, name="import_values"),
    path("imports/<int:pk>/preview/", views.import_preview, name="import_preview"),
    path("geocode/", views.geocode, name="geocode"),
    path("geocode/step/", views.geocode_step, name="geocode_step"),
    path("geocode/retry/", views.geocode_retry, name="geocode_retry"),
    path("lines/", views.lines, name="lines"),
    path("export/inventory.csv", views.export_inventory, name="export_inventory"),
    path("export/site.zip", views.export_site, name="export_site"),
    path("requests/", views.requests_list, name="requests"),
    path("requests/<int:pk>/", views.request_detail, name="request_detail"),
    path("photos/", views.photos_list, name="photos"),
    path("photos/<int:pk>/", views.photo_detail, name="photo_detail"),
    path("photos/<int:pk>/image/<int:which>/", views.photo_file, name="photo_file"),
    path("settings/", views.settings_redirect, name="settings"),
]
