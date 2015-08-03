# encoding: utf-8
"""Interact with the Akamai CCU API

`PurgeRequest` is a simple wrapper around the CCU REST API[1]_ using the
requests[2]_ library.

Example usage::

>>> from pprint import pprint
>>> from django_akamai.purge import PurgeRequest
>>> pr = PurgeRequest(username="ccuapi_user", password="1234567")
>>> pr.add("http://www.example.com/url-1.html")
>>> pr.add(u"http://www.example.com/url-2.html")
>>> response, number_of_urls = pr.purge()
>>> pprint(response)
{"detail": "Request accepted.",
 "estimatedSeconds": 420,
 "httpStatus": 201,
 "pingAfterSeconds": 420,
 "progressUri": "/ccu/v2/purges/…",
 "purgeId": "…",
 "supportId": "…"}
>>> print pr.last_response.status_code
201
>>> print pr.urls
[]
>>> pprint(pr.check_purge_status(response['progressUri']))
{"originalEstimatedSeconds": 420,
 "purgeId": "…",
 "originalQueueLength": 0,
 "supportId": "…",
 "httpStatus": 200,
 "completionTime": "2014-05-23T15:24:55Z",
 "submittedBy": "…",
 "purgeStatus": "Done",
 "submissionTime": "2014-05-23T15:21:00Z"}
>>> pprint(pr.check_queue_length())
{u'httpStatus': 200,
 u'detail': u'The queue may take a minute to reflect new or removed requests.',
 u'queueLength': 0,
 u'supportId': u'…'}

URLs can also be passed in when initially creating `PurgeRequest`. `QuerySet`s are
also supported for models which define `get_absolute_url()`.

The result of the request is returned when calling `purge()` and is also stored
in `PurgeRequest` as `self.last_response`.

Result codes follow this pattern (from the CCUAPI docs):
201 - The removal request has been accepted.
4xx - Invalid request
5xx - Contact Akamai support

Check `self.last_response['detail']` for more information related to the `httpStatus`
returned by the last purge request.

.. [1] See https://api.ccu.akamai.com/ccu/v2/docs/
.. [2] See http://python-requests.org/
"""
from __future__ import absolute_import

import json
from warnings import warn

import requests
from requests.auth import HTTPBasicAuth

from django.conf import settings
from django.db.models.query import QuerySet
from six.moves.urllib.parse import urljoin


class NoAkamaiUsernameProvidedException(Exception):
    pass


class NoAkamaiPasswordProvidedException(Exception):
    pass


class PurgeRequest(object):
    def __init__(self, username=None, password=None, options=None, urls=None,
                 ccu_base_url='https://api.ccu.akamai.com'):
        """
        PurgeRequest requires a username and password with access to the CCUAPI
        service. This can be passed in as an init argument or kept in the
        Django settings file.
        """

        self.ccu_base_url = ccu_base_url

        self.username = username
        if not username:
            self.username = getattr(settings, 'AKAMAI_CCUAPI_USERNAME', None)

        self.password = password
        if not password:
            self.password = getattr(settings, 'AKAMAI_CCUAPI_PASSWORD', None)

        if not self.username:
            raise NoAkamaiUsernameProvidedException
        if not self.password:
            raise NoAkamaiPasswordProvidedException

        self.http_auth = HTTPBasicAuth(self.username, self.password)

        """
        Get default options, then update with any user-provided options
        """
        if hasattr(settings, 'AKAMAI_CCUAPI_NOTIFICATION_EMAIL'):
            warn('''The AKAMAI_CCUAPI_NOTIFICATION_EMAIL setting is deprecated. '''
                 '''The new CCU purge API allows you to poll for purge status: '''
                 '''https://api.ccu.akamai.com/ccu/v2/docs/#section_CheckingPurgeStatus''',
                 DeprecationWarning)

        # See https://api.ccu.akamai.com/ccu/v2/docs/#section_PurgeRequest
        self.options = {'action': 'remove',
                        'type': 'arl',
                        'domain': 'production'}
        if options:
            self.options.update(options)

        """
        Define an empty urls list and add any urls provided when the
        instance is created.
        """
        self.urls = []

        if urls is not None:
            self.add(urls)

        # Used for storing the result of the last purge request
        self.last_response = None

    @property
    def last_result(self):
        warn('`last_result` has been replaced with `last_response`', DeprecationWarning)
        return self.last_response

    def add(self, urls=None):
        """
        Add the provided urls to this purge request

        The urls argument can be a single string, a list of strings, a queryset
        or object. Objects, including those contained in a queryset, must
        support get_absolute_url()
        """

        if urls is None:
            raise TypeError("add a URL, list of URLs, queryset or object")

        if isinstance(urls, (list, tuple)):
            self.urls.extend(urls)
        elif isinstance(urls, basestring):
            self.urls.append(urls)
        elif isinstance(urls, QuerySet):
            for obj in urls:
                self.urls.append(obj.get_absolute_url())
        elif hasattr(urls, 'get_absolute_url'):
            self.urls.append(urls.get_absolute_url())
        else:
            raise TypeError("Don't know how to handle %r" % urls)

    def purge(self, purge_batch_size=200):
        """Issue a purge request

        Only `purge_batch_size` urls will be sent in a single purge request. If self.urls contains more
        items, purge() will need to be called multiple times

        On success, returns the decoded JSON result of the purge request and the number of urls sent in the
        request.
        On error, returns None. The full `Response` object is available as
        """

        self.last_response = None

        urls_slice = self.urls[:purge_batch_size]

        if urls_slice:
            purge_url = urljoin(self.ccu_base_url, '/ccu/v2/queues/default')

            data = {'type': self.options['type'],
                    'domain': self.options['domain'],
                    'objects': urls_slice}

            self.last_response = requests.post(url=purge_url, data=json.dumps(data),
                                               auth=self.http_auth,
                                               headers={'Content-Type': 'application/json'})

            if self.last_response.ok:
                self.urls = self.urls[purge_batch_size:]
                return self.last_response.json(), len(urls_slice)
            else:
                return None, 0

    def purge_all(self):
        """
        Purges all URLs by calling purge() until self.urls is empty

        Returns a list containing the results of each request.
        """
        results = []
        while self.urls:
            purge_result = self.purge()
            results.append(purge_result)
        return results

    def check_purge_status(self, progress_uri):
        """
        Check the status of a purge request using the ``progressUri`` value obtained from a previous purge
        request

        Returns the decoded JSON response::

        {
            "originalEstimatedSeconds": 420,
            "purgeId": "…",
            "originalQueueLength": 0,
            "supportId": "…",
            "httpStatus": 200,
            "completionTime": "2014-05-23T15:24:55Z",
            "submittedBy": "…",
            "purgeStatus": "Done",
            "submissionTime": "2014-05-23T15:21:00Z"
        }
        """

        resp = requests.get(url=urljoin(self.ccu_base_url, progress_uri),
                            auth=self.http_auth)
        return resp.json()

    def check_queue_length(self):
        """Check the current length of the purge request queue

        Returns the decoded JSON response::

        {
            u'httpStatus': 200,
            u'detail': u'The queue may take a minute to reflect new or removed requests.',
            u'queueLength': 0,
            u'supportId': u'…'
        }
        """
        resp = requests.get(url=urljoin(self.ccu_base_url, '/ccu/v2/queues/default'),
                            auth=self.http_auth)
        return resp.json()
