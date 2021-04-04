from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('<letter>', views.index, name='index'),
    path('<letter>/<page>', views.index, name='index')
]