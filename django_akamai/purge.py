# encoding: utf-8
"""
purge.py

Example usage:

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

URLs can also be passed in when initially creating PurgeRequest. QuerySets are
also supported, but each object in the set must have get_absolute_url()
defined on the model.

The result of the request is returned when calling purge() and is also stored
in PurgeRequest as last_result.

Result codes follow this pattern (from the CCUAPI docs):
1xx - Successful Request
2xx - Warning; reserved. The removal request has been accepted.
3xx - Bad or invalid request.
4xx - Contact Akamai Customer Care.

Check last_result['resultMsg'] for more information related to the resultCode
returned by the last purge request.

IMPORTANT NOTE: The CCUAPI only supports "about" 100 URLs per purge request.
For this reason, purge() will only attempt to purge 100 URLs at a time, and
subsequent calls to purge() will be required to purge all URLs.
"""
from __future__ import absolute_import

import os.path

from django.conf import settings
from django.db.models.query import QuerySet

from suds.client import Client


class NoAkamaiUsernameProvidedException(Exception):
    pass


class NoAkamaiPasswordProvidedException(Exception):
    pass


class PurgeRequest(object):

    def __init__(self, username=None, password=None,
                 options=None, urls=None, wsdl=None):
        """
        PurgeRequest requires a username and password with access to the CCUAPI
        service. This can be passed in as an init argument or kept in the
        Django settings file.

        By default, the WSDL is expected to be in the same directory as this
        file, unless an absolute path is passed in via the wsdl argument. One
        word of caution when passing in a non-default WSDL file: the file
        included with this module has been edited to include the xmlsoap.org
        SOAP encoding schema in the WSDL types definition (line 25). A non-
        default file may not be valid for usage with suds, resulting in
        various type-related errors.
        """
        self.wsdl = wsdl
        if not self.wsdl:
            self.wsdl = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     'ccuapi-axis.wsdl')
        self.client = Client("file://%s" % self.wsdl)
        self.username = username
        if not username:
            self.username = getattr(settings, 'AKAMAI_CCUAPI_USERNAME', None)
            if not self.username:
                raise NoAkamaiUsernameProvidedException
        self.password = password
        if not password:
            self.password = getattr(settings, 'AKAMAI_CCUAPI_PASSWORD', None)
            if not self.password:
                raise NoAkamaiPasswordProvidedException

        """
        Get default options, then update with any user-provided options
        """
        self.options = self.default_options()
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
        self.last_result = None

    def add(self, urls=None):
        """
        Add the provided urls to this purge request

        The urls argument can be a single string, a list of strings, a queryset
        or object. Objects, including those contained in a queryset, must
        support get_absolute_url()
        """

        if urls is None:
            raise TypeError("add a URL, list of URLs, queryset or object")

        if isinstance(urls, list):
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
        """
        Perform the service's purgeRequest method.

        Options are required to be in a list of strings format, so self.options
        is converted to such before performing the call.

        The '' argument in purgeRequest takes the place of a deprecated
        network parameter and now requires an empty string.

        Only 100 urls will be sent in the purge request, due to limits set
        by Akamai. If self.urls contains more than 100 urls, purge() will
        need to be called until none remain.

        Returns the result of the purge request and the number of urls sent
        in the request.
        """
        urls_slice = self.urls[:100]
        num_purged_urls = len(urls_slice)
        self.last_result = None
        if urls_slice:
            self.last_result =\
                self.client.service.purgeRequest(self.username,
                                                 self.password,
                                                 '',
                                                 self.convert_options(),
                                                 urls_slice)
            self.urls = self.urls[100:]
        return self.last_result, num_purged_urls

    def purge_all(self):
        """
        Purges all URLs in self.urls in batches of 100 using purge()

        Returns a list containing the results of each request.
        """
        results = []
        while self.urls:
            purge_result = self.purge()
            results.append(purge_result)
        return results

    def convert_options(self):
        """
        Return the self.options dict as a list of strings in "k=v" format.
        """
        return ["%s=%s" % (k, v) for k, v in self.options.items()]

    @classmethod
    def default_options(self):
        email_notify_addr = getattr(settings,
                                    'AKAMAI_CCUAPI_NOTIFICATION_EMAIL', '')

        return {"email-notification-name": email_notify_addr,
                "action": "remove",      # or 'invalidate'
                "type": "arl",           # or 'cpcode'
                "domain": "production"}  # or 'staging'
