from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.i18n import set_language

from pipetrace.core import views as core_views

urlpatterns = [
    path("", core_views.root, name="root"),
    path("healthz", core_views.healthz, name="healthz"),
    path("robots.txt", core_views.robots, name="robots"),
    path("i18n/setlang/", set_language, name="set_language"),
    path("api/", include("pipetrace.residents.api_urls")),
    path("staff/", include("pipetrace.staff.urls")),
    path("admin/", admin.site.urls),
]

urlpatterns += i18n_patterns(
    path("", include("pipetrace.residents.urls")),
    prefix_default_language=True,
)

urlpatterns += [
    # A Protomaps .pmtiles extract of the service area (see docs/basemap.md).
    re_path(r"^basemap/(?P<path>.+)$", core_views.basemap, name="basemap"),
]

handler404 = "pipetrace.core.views.not_found"
handler500 = "pipetrace.core.views.server_error"
