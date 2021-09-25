from django.urls import path

from . import views
from .models import KRL_ABC


urlpatterns = [
    path('', views.index, name='index'),
    # TODO: combine similar
    path('about/', views.AboutPageView.as_view(), name='about'),
    path('search', views.search_proc, name='search_proc'),
    path('search/', views.search_proc, name='search_proc'),
    path('search/<str:query>', views.search, name='search'),
    path('search/<str:query>/<int:page>', views.search, name='search'),
    path('<letter>/', views.index, name='index'),  # TODO: filter letter one char in KRL
    path('<letter>/<int:page>', views.index, name='index'),  # TODO: filter letter one char in KRL
]
