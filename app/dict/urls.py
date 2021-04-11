from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    # TODO: combine simular
    path('search', views.search_proc, name='search_proc'),
    path('search/', views.search_proc, name='search_proc'),
    path('search/<query>', views.search, name='search'),
    path('search/<query>/<int:page>', views.search, name='search'),
    path('<letter>', views.index, name='index'),
    path('<letter>/<int:page>', views.index, name='index'),
]
