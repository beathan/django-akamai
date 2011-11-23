# encoding: utf-8
"""
Defines a django-celery task to queue a purge request

Usage:
>>> PurgeRequestTask.delay(sender)

'sender' can be a URL string, a list of URL strings, or a Django object or
Queryset, so long as get_absolute_url() is defined for those objects.
"""
from __future__ import absolute_import

from celery.task import Task

from .purge import PurgeRequest


class PurgeRequestTask(Task):
    default_retry_delay = 60 * 2 # seconds here, so 2 minutes total
    max_retries = 5

    def run(self, urls, **kwargs):
        pr = PurgeRequest(urls=urls)
        result, num_urls = pr.purge()
        return num_urls
