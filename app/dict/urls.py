from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('search', views.search_proc, name='search_proc'),
    path('search/', views.search_proc, name='search_proc'),
    path('search/<query>', views.search, name='search'),
    path('search/<query>/<page>', views.search, name='search'),
    path('<letter>', views.index, name='index'),
    path('<letter>/<page>', views.index, name='index'),
]
