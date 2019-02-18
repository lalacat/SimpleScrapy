from utils.record_live_instances import object_ref
from twisted.web.http_headers import Headers
from utils.urllibs import safe_url_string,escape_ajax
from https.parse_url import to_bytes


class Request(object_ref):
    def __init__(self,url,callback=None,method='GET',headers=None,
                body=None,cookies=None,meta=None,encoding='UTF-8',
                 dont_filter=False,errback=None,flags=None):
        self._encoding = encoding  # this one has to be set first
        self.method = str(method).upper()
        self._set_url(url)
        self.body = body #用于存储发送给网站的内容

        if callback is not None and not callable(callback):
            raise TypeError('callback 回调函数必须是可执行的，得到的是：%s' % type(callback).__name__)
        if errback is not None and not callable(errback):
            raise TypeError('errback 回调函数必须是可执行的，得到的是：%s' % type(callback).__name__)
        assert callback or not errback,'不能只设置errback而没有callback'
        self.callback = callback
        self.errback = errback

        self.cookies = cookies or {}
        self.headers = Headers(headers or {})
        self.dont_filter = dont_filter #过滤标准位

        self._meta = dict(meta) if meta else None
        self.flags = [] if flags is None else list(flags)

    @property
    def meta(self):
        if self._meta is None :
            self._meta = {}
        return self._meta

    def _get_url(self):
        return self._url

    def _set_url(self,url):
        if not isinstance(url,str):
            raise TypeError('Request url must be str or unicode, got %s:' % type(url).__name__)

        s = safe_url_string(url,encoding=self._encoding)
        self._url = escape_ajax(s)

        if ":" not in self._url:
            raise ValueError('url缺少scheme: %s '%self._url)

    url = property(_get_url,_set_url)

    @property
    def body(self):
        return self._body

    @body.setter
    def body(self,body):
        if body is None:
            self._body = b''
        else:
            self._body = to_bytes(body,self.encoding)


    @property
    def encoding(self):
        return self._encoding

    def __str__(self):
        return "<%s %s>" %(self.method,self.url)

    __repr__ = __str__

    def copy(self):
        return self.replace()

    def replace(self, *args, **kwargs):
        """Create a new Request with the same attributes except for those
        given new values.
        """
        for x in ['url', 'method', 'headers', 'body', 'cookies', 'meta',
                  'encoding', 'priority', 'dont_filter', 'callback', 'errback']:
            kwargs.setdefault(x, getattr(self, x))
        cls = kwargs.pop('cls', self.__class__)
        return cls(*args, **kwargs)

