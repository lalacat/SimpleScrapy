import base64
import logging
from urllib.parse import urlunparse

logger = logging.getLogger(__name__)


class AddHttpProxy(object):

    def __init__(self,logformatter=None,auth_encoding='utf-8'):
        self.auth_encoding = auth_encoding
        self.lfm = logformatter
        if self.lfm:
            logger.info(*self.lfm.crawled(
                "DownloadMidder",self.__class__.__name__,
                '已初始化！！'
            ))

    @classmethod
    def from_crawler(cls,crawler):
        logformatter = crawler.logformatter
        auth_encoding = crawler.settings.get('HTTPPROXY_AUTH_ENCODING')
        return cls(logformatter,auth_encoding)

    def _basic_auth_header(self,cred):
        user_pass = base64.b64encode(cred.encode(self.auth_encoding)).strip()
        return b'Basic '+ user_pass

    def _get_proxy(self,proxy):
        if len(proxy) == 2:
            proxy += (None,)
        try:
            hostname, hostport, creds = proxy
            proxy_url = urlunparse((hostname, str(hostport), '', '', '', ''))
            if creds:
                creds = self._basic_auth_header(creds)
        except Exception as e :
            print(e)
        return creds,proxy_url

    def process_request(self,request,spider):
        # proxy配置格式tuple
        # (hostname,port,crdes)
        proxy = request.meta.get('proxy_config')
        if proxy:
            creds,proxy_url = self._get_proxy(proxy)
            request.meta['proxy'] = proxy_url
            if creds and not request.headers.getRawHeaders('Proxy-Authorization'):
                request.headers.setRawHeaders('Proxy-Authorization',[creds])

        return  None
