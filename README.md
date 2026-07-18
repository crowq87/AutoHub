# 🚗 AutoHub — Vehicle Marketplace

A Django web application for buying, selling, and renting vehicles in Pinamungajan and Toledo, Cebu.

## 📁 Project Structure


autohub_project/
├── autohub/              ← Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── core/                 ← Main app
│   ├── models.py         ← Database models
│   ├── views.py          ← Page logic
│   ├── forms.py          ← Forms
│   ├── urls.py           ← URL routes
│   ├── admin.py          ← Admin panel config
│   └── signals.py        ← Auto-notifications
├── templates/core/       ← All HTML pages
│   ├── base.html         ← Navbar + Footer layout
│   ├── home.html         ← Public homepage
│   ├── login.html
│   ├── signup.html
│   ├── dashboard.html    ← Browse listings
│   ├── vehicle_detail.html
│   ├── post_vehicle.html ← Post/Edit listing
│   ├── my_profile.html
│   ├── notifications.html
│   ├── about.html
│   ├── admin_dashboard.html
│   └── admin_users.html
├── static/css/
│   └── style.css
├── requirements.txt
├── manage.py
└── .env.example

- **Backend:** Python 3.10 + Django 4.2
- **Database:** PostgreSQL
- **Image Storage:** Cloudinary
- **Frontend:** Bootstrap 5 + Poppins font
- **Icons:** Bootstrap Icons
- **Hosting:** PythonAnywhere
