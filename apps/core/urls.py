from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("_styleguide/", views.styleguide, name="styleguide"),
]
