from django.urls import path

from . import views
from .models import KRL_ABC


urlpatterns = [
    path('', views.index, name='index'),
    # TODO: combine similar
    path('about/', views.AboutPageStaticView.as_view(), name='about'),
    path('intro/', views.IntroStaticView.as_view(), name='intro'),
    path('punzhina/', views.PunzhStaticView.as_view(), name='punzh'),
    path('dialects/', views.DialectsStaticView.as_view(), name='dialects'),
    path('team/', views.TeamStaticView.as_view(), name='team'),
    path('search', views.search_proc, name='search_proc'),
    path('search/', views.search_proc, name='search_proc'),
    path('search/<str:query>', views.search, name='search'),
    path('search/<str:query>/<int:page>', views.search, name='search'),
    path('<letter>/', views.index, name='index'),  # TODO: filter letter one char in KRL
    path('<letter>/<int:page>', views.index, name='index'),  # TODO: filter letter one char in KRL
]
