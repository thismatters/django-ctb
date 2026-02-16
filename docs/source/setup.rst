=============================
Setup
=============================

-----------------------------
Installation
-----------------------------

Django CTB is a pretty normal Django package. The installation goes about like you'd expect::

  pip install django-ctb


By default this project uses `Dramatiq <https://dramatiq.io/>`_ for handling background tasks. It is entirely possible to integrate this app without Dramatiq, but you'll have to do your own integration there.

If you want to install Dramatiq automatically you can use::

  pip install django-ctb[dramatiq]

Please see the ``dramatiq`` docs for appropriate configuration of that package.

-----------------------------
Configuration
-----------------------------

Once the package is installed you'll need to add it to your django project by updating the ``INSTALLED_APPS`` list in ``settings.py``::

  INSTALLED_APPS = [
      ...
      "django_ctb",
      ...
  ]


