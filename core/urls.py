from django.urls import path
from . import views

urlpatterns = [
    # Public
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),

    # Auth
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),

    # User
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.my_profile, name='my_profile'),
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/<int:pk>/read/', views.mark_notif_read, name='mark_notif_read'),

    # Listings
    path('vehicles/<int:pk>/', views.vehicle_detail, name='vehicle_detail'),
    path('vehicles/post/', views.post_vehicle, name='post_vehicle'),
    path('vehicles/<int:pk>/edit/', views.edit_vehicle, name='edit_vehicle'),
    path('vehicles/<int:pk>/delete/', views.delete_vehicle, name='delete_vehicle'),
    path('photos/<int:photo_id>/delete/', views.delete_photo, name='delete_photo'),

    # Admin
    path('admin-panel/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-panel/users/', views.admin_users, name='admin_users'),
    path('admin-panel/listings/<int:pk>/approve/', views.admin_approve_listing, name='admin_approve_listing'),
    path('admin-panel/listings/<int:pk>/remove/', views.admin_remove_listing, name='admin_remove_listing'),

]