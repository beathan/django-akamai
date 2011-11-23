# encoding: utf-8
"""
This module defines two signals, one that initiates a purge request directly,
and another that queues the request. The queueing signal is conditionally
defined and depends on the successful import of PurgeRequestTask, which depends
on django-celery being installed.

When sending these signals from other apps, you can pass in a variety of things
as the sender for convenience. Sender can be a single URL string, a list of
URL strings, an individual Django object, or a QuerySet. If passing in an
object or QuerySet, then get_absolute_url() must be defined on every object.

Example:
>>> obj = MyObject.objects.get(pk=3)
>>> obj.get_absolute_url()
u'http://www.example.com/blahblah.html'
>>> purge_request.send(obj)

Or:
>>> queue_purge_request.send(obj)
"""
from __future__ import absolute_import

from django.dispatch import Signal

from .purge import PurgeRequest

try:
    from .tasks import PurgeRequestTask
except:
    tasks_available = False
else:
    tasks_available = True


purge_request = Signal()

def purge_request_handler(sender, **kwargs):
    pr = PurgeRequest()
    pr.add(sender.get_absolute_url())
    result = pr.purge()
    return result

purge_request.connect(purge_request_handler)


if tasks_available:
    queue_purge_request = Signal()

    def queue_purge_request_handler(sender, **kwargs):
        result = PurgeRequestTask.delay(sender)

    queue_purge_request.connect(queue_purge_request_handler)
