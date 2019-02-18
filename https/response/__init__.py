from utils.record_live_instances import object_ref
from urllib.parse import urljoin

class Response(object_ref):

    def __init__(self, url, status=200, headers=None, body=b'', flags=None, request=None):
       self.headers = headers or {}
       self.status = int(status)
       self._set_body(body)
       self._set_url(url)
       self.request = request
       self.flags = [] if flags is None else list(flags)


    @property
    def meta(self):
        try:
            return self.request.meta
        except AttributeError:
            raise AttributeError(
                "Response.meta 不可用，这个response没有绑定任何的request"
            )

    def _get_url(self):
        return self._url

    def _set_url(self,url):
        if isinstance(url,str):
            self._url = url
        else:
            raise TypeError('%s url must be str, got %s:' % (type(self).__name__,
                                                             type(url).__name__))
    url = property(_get_url,_set_url)

    def _get_body(self):
        return self._body

    def _set_body(self,body):
        if body is None:
            self._body = b''
        elif not isinstance(body,bytes):
            raise TypeError("Response body 必须是bytes类型")
        else:
            self._body = body

    body = property(_get_body,_set_body)

    def __str__(self):
        return "<%d %s>" % (self.status, self.url)

    __repr__ = __str__

    def copy(self):
        """Return a copy of this Response"""
        return self.replace()

    def replace(self, *args, **kwargs):
        """Create a new Response with the same attributes except for those
        given new values.
        """
        for x in ['url', 'status', 'headers', 'body', 'request', 'flags']:
            kwargs.setdefault(x, getattr(self, x))
        cls = kwargs.pop('cls', self.__class__)
        return cls(*args, **kwargs)

    def urljoin(self, url):
        """Join this Response's url with a possible relative url to form an
        absolute interpretation of the latter."""
        return urljoin(self.url, url)



