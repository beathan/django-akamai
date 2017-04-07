django-akamai
=============

Dependencies: requests_ (required), django-celery_ (optional)

.. _requests: http://python-requests.org/
.. _django-celery: http://github.com/ask/django-celery

django-akamai serves as a means to perform purge requests from Django apps
using the Akamai REST API. Purge requests are performed on demand or, optionally,
placed in a queue using Celery.

Configuration
-------------

This library uses the edgegrid-python_ client for authentication. If the
`~/.edgerc` config file contains a `CCU` section those credentials will be used
automatically.

To specify a different location for the edgerc file, you may use these Django
settings::

    AKAMAI_EDGERC_FILENAME
    AKAMAI_EDGERC_CCU_SECTION

If you prefer to keep the values in your Django settings you may specify them
directly:

    AKAMAI_CCU_CLIENT_SECRET
    AKAMAI_CCU_HOST
    AKAMAI_CCU_ACCESS_TOKEN
    AKAMAI_CCU_CLIENT_TOKEN

For simplicity and security use of the `.edgerc` file is recommended.

Consult Akamai's documentation for full information about the API:

https://developer.akamai.com/api/purge/ccu/overview.html

.. _edgegrid-python: https://pypi.python.org/pypi/edgegrid-python


Directly issuing purge requests
-------------------------------

You may import ``PurgeRequest`` from ``django_akamai.purge`` and provide it with
one or more URLs to invalidate or delete.

Note that Akamai's API specifies a byte limit on the number of requests and a
single purge call may require multiple HTTP requests to complete.

TODO: discuss options for rate-limiting

Example:
::

    >>> pr = PurgeRequest()
    >>> pr.add("http://www.example.com/url-1.html")
    >>> pr.add(u"http://www.example.com/url-2.html")
    >>> for url_batch, response in pr.purge():
        print(resp.status_code, len(url_batch))
    201 2
    >>> print pr.urls
    []


Using Django Signals
--------------------

``django_akamai.signals`` defines two signals to directly issue a purge request
or, when Celery is available, queue the request.

When sending these signals from other apps, you can pass in a variety of things
as the sender for convenience. Sender can be a single URL string, a list of
URL strings, an individual Django object, or a QuerySet. If passing in an
object or QuerySet, then ``get_absolute_url()`` must be defined on every object.

Example of signalling to immediately perform the request:
::

    >>> from django_akamai.signals import purge_request, queue_purge_request
    >>> obj = MyObject.objects.get(pk=3)
    >>> obj.get_absolute_url()
    u'http://www.example.com/blahblah.html'
    >>> purge_request.send(obj)

Or, to queue the request using Celery:
::

    >>> queue_purge_request.send(obj)


Using Tasks
-----------
To use the task directly, import ``PurgeRequestTask`` from tasks.py thusly:
::

    >>> from akamai.tasks import PurgeRequestTask
    >>> obj = MyObject.objects.get(pk=3)
    >>> PurgeRequestTask.delay(obj)
