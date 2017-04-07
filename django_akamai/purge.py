# encoding: utf-8
"""Interact with the Akamai CCU API

`PurgeRequest` is a simple wrapper around the CCU REST API[1]_ using the
requests[2]_ library.

Example usage::

>>> from pprint import pprint
>>> from django_akamai.purge import PurgeRequest
>>> pr = PurgeRequest()
>>> pr.add("http://www.example.com/url-1.html")
>>> pr.add(u"http://www.example.com/url-2.html")
>>> pr.purge_all()
>>> pr.add(large_collection_of_urls)
>>> for url_batch, response in pr.purge(): print(response.status_code)
201
201
201
507

URLs can also be passed in when initially creating `PurgeRequest` and will be
passed to `PurgeRequest.add()` verbatim.

In addition to the single URLs shown in the example above `PurgeRequest.add()`
accepts lists or tuples of URLs as well as Django Model and QuerySet instances
which implement `get_absolute_url()`.

For general usage, `purge_all()` is recommended but `purge()` allows you to
receive more information while requests are pending and possibly implement your
own

Result codes follow this pattern from the CCU API docs:
201 - The removal request has been accepted.
4xx - Invalid request
507 - API rate-limit – try again later
5xx - Contact Akamai support

API responses should be JSON objects containing a `detail` element with
additional information.

.. [1] See https://developer.akamai.com/api/purge/ccu/overview.html
.. [2] See http://python-requests.org/
"""

from __future__ import absolute_import

import json
import logging
import os
import time

import requests
from akamai.edgegrid import EdgeGridAuth, EdgeRc
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models.query import QuerySet

from six.moves.urllib.parse import urljoin

logger = logging.getLogger(__name__)


class InvalidAkamaiConfiguration(ImproperlyConfigured):
    pass


def load_edgegrid_client_settings():
    '''Load Akamai EdgeGrid configuration

    returns a (hostname, EdgeGridAuth) tuple from the following locations:

    1. Values specified directly in the Django settings::
        AKAMAI_CCU_CLIENT_SECRET
        AKAMAI_CCU_HOST
        AKAMAI_CCU_ACCESS_TOKEN
        AKAMAI_CCU_CLIENT_TOKEN
    2. An edgerc file specified in the AKAMAI_EDGERC_FILENAME settings
    3. The default ~/.edgerc file

    Both edgerc file load options will return the values from the “CCU” section
    by default. This may be customized using the AKAMAI_EDGERC_CCU_SECTION setting.
    '''

    if getattr(settings, 'AKAMAI_CCU_CLIENT_SECRET', None):
        # If the settings module has the values directly and they are not empty
        # we'll use them without checking for an edgerc file:

        host = settings.AKAMAI_CCU_HOST
        auth = EdgeGridAuth(access_token=settings.AKAMAI_CCU_ACCESS_TOKEN,
                            client_token=settings.AKAMAI_CCU_CLIENT_TOKEN,
                            client_secret=settings.AKAMAI_CCU_CLIENT_SECRET)
        return host, auth
    else:
        edgerc_section = getattr(settings, 'AKAMAI_EDGERC_CCU_SECTION', 'CCU')

        edgerc_path = getattr(settings, 'AKAMAI_EDGERC_FILENAME', '~/.edgerc')
        edgerc_path = os.path.expanduser(edgerc_path)

        if os.path.isfile(edgerc_path):
            edgerc = EdgeRc(edgerc_path)
            host = edgerc.get(edgerc_section, 'host')
            auth = EdgeGridAuth.from_edgerc(edgerc, section=edgerc_section)
            return host, auth

        raise InvalidAkamaiConfiguration('Cannot find Akamai client configuration!')


class PurgeRequest(object):
    #: 50KB limit from https://developer.akamai.com/api/purge/ccu/overview.html#limits allowing for overhead
    MAX_REQUEST_SIZE = 45000

    def __init__(self, urls=None, action='delete', network='production',
                 edgegrid_host=None, edgegrid_auth=None):
        """Issue purge requests for the provided URL(s)

        `urls` may be a single string, a list or tuple, or a Django QuerySet or
        Model instance which implements `get_absolute_url()` — see `add()`.

        `action` is passed directly to the API and has the same options documented
        by Akamai. Currently it should be either `invalidate` or `delete`.

        `network` is passed directly to the API and has the same options documented
        by Akamai. Currently it should be either `staging` or `production`.

        Authentication is performed by the edgegrid-python library. If you wish to
        provide the host and a configured EdgeGridAuth instance you may pass those
        values directly. Otherwise, values will be obtained from the sources
        supported by the `load_edgegrid_client_settings()` function.

        See https://developer.akamai.com/api/purge/ccu/overview.html
        and https://developer.akamai.com/api/purge/ccu/resources.html
        """

        if edgegrid_auth is not None and edgegrid_host is not None:
            self.host = edgegrid_host
            self.auth = edgegrid_auth
        else:
            self.host, self.auth = load_edgegrid_client_settings()

        self.action = action
        self.network = network

        self.urls = []

        if urls is not None:
            self.add(urls)

    def add(self, urls):
        """
        Add the provided urls to this purge request

        The urls argument can be a single string, a list of strings, a queryset
        or model instance. Models must implement `get_absolute_url()`.
        """

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

    def purge(self):
        """Submit purge request(s) to the CCU API

        Since a purge call may require multiple API requests and may trigger rate-limiting
        this method uses a generator to provide the results of each request, allowing you to
        communicate request progress or implement a custom rate-limiting response::

            for url_batch, response in purge_request.purge():
                if response.ok:
                    # update progress
                elif response.status_code == 507:
                    # Rate-limiting. Do something?

        If you simply want a function which blocks until all of the purge requests have been
        issued, use `purge_all()`.

        Both `purge()` and `purge_all()` will raise HTTP exceptions for any error response
        other than rate-limiting.
        """

        purge_url = urljoin('https://%s' % self.host, '/ccu/v3/%s/url/%s' % (self.action, self.network))

        while self.urls:
            # We'll accumulate
            batch = []
            batch_size = 0

            while self.urls and batch_size < self.MAX_REQUEST_SIZE:
                next_url = self.urls.pop()

                if not isinstance(next_url, bytes):
                    next_url = next_url.encode('utf-8')

                batch.append(next_url)
                batch_size += len(next_url)

            if batch:
                data = {'objects': batch}

                logger.debug('Requesting Akamai purge %d URLs', len(batch))

                response = requests.post(url=purge_url, auth=self.auth, data=json.dumps(data),
                                         headers={'Content-Type': 'application/json'})

                if not response.ok:
                    # We'll return the current batch to the queue so they can be retried later:
                    self.urls.extend(batch)

                    # Raise an exception for errors other than rate-limiting:
                    if response.status_code != 507:
                        response.raise_for_status()

                yield batch, response

    def purge_all(self, rate_limit_delay=60):
        '''Purge all pending URLs, waiting for API rate-limits if necessary!'''

        for batch, response in self.purge():
            if response.status_code == 507:
                details = response.json().get('detail', '<response did not contain "detail">')
                logger.info('Will retry request in %d seconds due to API rate-limit: %s',
                            rate_limit_delay, details)
                time.sleep(rate_limit_delay)

    def check_purge_status(self, progress_uri):
        raise DeprecationWarning('The CCU v3 API does not support purge status checks')

    def check_queue_length(self):
        raise DeprecationWarning('The CCU v3 API does not support queue length checks')
