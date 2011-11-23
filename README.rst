django-akamai
=============

Dependencies: suds_ (required), django-celery_ (optional)

.. _suds: https://fedorahosted.org/suds/
.. _django-celery: http://github.com/ask/django-celery

django-akamai serves as a means to perform purge requests from Django apps
using the Akamai CCUAPI. Purge requests are performed on demand or, optionally,
placed in a queue using Celery.

Required settings:
::

	AKAMAI_CCUAPI_USERNAME = 'ccuapi_username'
	AKAMAI_CCUAPI_PASSWORD = 'ccuapi_password'
	AKAMAI_CCUAPI_NOTIFICATION_EMAIL = 'your@email.com'

There are a variety of ways to use this app in your app.

**PLEASE NOTE**: Currently, only 100 URLs will be purged per request, requiring
that you send additional signals/create additional tasks/call purge() again with
separate chunks of URLs/objects. The CCUAPI imposes a limit of "about" 100 URLs
of 400 characters each, so I have attempted to make the behavior transparent and
allow the end user to see the result of each request and respond accordingly.

Consult Akamai's documentation_ for full information about the API. This app
comes bundled with a modified copy of https://ccuapi.akamai.com/ccuapi-axis.wsdl
which works with suds.

.. _documentation: https://control.akamai.com/dl/customers/other/CCU/Content_Control_Interfaces.pdf

Using Signals
-------------
signals.py defines two signals, one that initiates a purge request directly,
and another that queues the request. The queueing signal is conditionally
defined and depends on the successful import of PurgeRequestTask, which depends
on django-celery being installed.

When sending these signals from other apps, you can pass in a variety of things
as the sender for convenience. Sender can be a single URL string, a list of
URL strings, an individual Django object, or a QuerySet. If passing in an
object or QuerySet, then get_absolute_url() must be defined on every object.

Example of signalling to immediately perform the request:
::

	>>> from akamai.signals import purge_request, queue_purge_request
	>>> obj = MyObject.objects.get(pk=3)
	>>> obj.get_absolute_url()
	u'http://www.example.com/blahblah.html'
	>>> purge_request.send(obj)

Or, to queue the request using Celery:
::

	>>> queue_purge_request.send(obj)


Using Tasks
-----------
To use the task directly, import PurgeRequestTask from tasks.py thusly:
::

	>>> from akamai.tasks import PurgeRequestTask
	>>> obj = MyObject.objects.get(pk=3)
	>>> result = PurgeRequestTask.delay(obj)
	>>> print result
	1

Using PurgeRequest directly
---------------------------
You may also import PurgeRequest from purge.py and use it directly. Not that
only 100 urls will be sent with each purge request, due to limits set by Akamai.
If you add more than 100 urls, purge() will need to be called until none remain.

If you don't provide a username and password when creating the PurgeRequest
object, then your project's settings.py will be checked for
AKAMAI_CCUAPI_USERNAME and AKAMAI_CCUAPI_PASSWORD. Failure to provide login info
via either mechanism results in a NoAkamaiUsernameProvidedException and/or
NoAkamaiPasswordProvidedException.

Example:
::

	>>> pr = PurgeRequest(username="ccuapi_user", password="1234567")
	>>> pr.add("http://www.example.com/url-1.html")
	>>> pr.add(u"http://www.example.com/url-2.html")
	>>> req = pr.purge()
	>>> print pr.last_result
	(PurgeResult){
	   resultCode = 100
	   resultMsg = "Success."
	   sessionID = "987654321"
	   estTime = 420
	   uriIndex = -1
	   modifiers[] = <empty>
	 }
	>>> print pr.urls
	[]
