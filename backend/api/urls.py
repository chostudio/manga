from django.urls import path

from api.views.search import search as search_view
from api.views.upload import upload as upload_view
from api.views.upload_webscrape import upload_webscrape as upload_webscrape_view

urlpatterns = [
    path("search", search_view, name="search"),
    path("upload", upload_view, name="upload"),
    path("upload-webscrape", upload_webscrape_view, name="upload-webscrape"),
]
