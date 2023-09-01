from django.urls import path

from . import views


urlpatterns = [
    path('about/', views.StaticView.as_view(template_name='staticPages/about.html'), name='about'),
    path('intro/', views.StaticView.as_view(template_name='staticPages/intro.html'), name='intro'),
    path('punzhina/', views.StaticView.as_view(template_name='staticPages/punzh.html'), name='punzh'),
    path('dialects/', views.StaticView.as_view(template_name='staticPages/dialects.html'), name='dialects'),
    path('team/', views.StaticView.as_view(template_name='staticPages/team.html'), name='team'),

    path('search', views.search_proc, name='search_proc'),
    path('search/', views.search_proc, name='search_proc'),
    path('search/<str:query>', views.search, name='search'),
    path('search/<str:query>/<int:page>', views.search, name='search'),

    path('tags/', views.tag_search, name='tags'),
    path('tags/<str:tags>', views.tag_search, name='tags'),
    path('tags/<str:tags>/<int:page>', views.tag_search, name='tags'),

    path('', views.index, name='index'),
    path('<letter>/', views.index, name='index'),  # TODO: filter letter one char in KRL
    path('<letter>/<int:page>', views.index, name='index'),
]
