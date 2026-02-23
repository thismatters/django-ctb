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

This package optionally integrates with the
`Mouser Search API <https://www.mouser.com/api-search/>`_ for gathering
information about parts (pricing, names, and values of certain fields).
This integration allows the user to place part numbers in their bill of
materials, and the Clear to Build sync process will create the part and
populate the data from Mouser without user intervention.

To utilize this integration put your API key into settings.py thusly::

  CTB_MOUSER_API_KEY = "this-is-not-my-real-key"

.. note::
  Ironically, that is my real key...

