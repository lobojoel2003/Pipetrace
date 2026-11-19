from django.urls import path

from pipetrace.residents import api

app_name = "api"

urlpatterns = [
    path("search/", api.search_api, name="search"),
    path("lines.geojson", api.lines_geojson, name="lines"),
    path("stats.json", api.stats_api, name="stats"),
    path("search-index.json", api.search_index_api, name="search_index"),
    path("submit/", api.submit_api, name="submit"),
]
