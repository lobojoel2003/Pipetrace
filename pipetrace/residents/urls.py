from django.urls import path

from pipetrace.residents import views

app_name = "residents"

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.search_view, name="search"),
    path("line/<slug:public_id>/", views.line_view, name="line"),
    path("check-your-pipe/", views.guide, name="guide"),
    path("check-your-pipe/send-photo/", views.send_photo, name="send_photo"),
    path("request-inspection/", views.request_inspection, name="request_inspection"),
    path("thanks/<str:reference>/", views.thanks, name="thanks"),
    path("filters/", views.filters, name="filters"),
    path("about/", views.about, name="about"),
    path("streets/", views.streets, name="streets"),
    path("streets/<slug:slug>/", views.street, name="street"),
]
