from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def home(request: HttpRequest) -> HttpResponse:
    # Placeholder until the editorial home page (Phase 2, SPEC §6.1).
    return render(request, "pages/home.html")
