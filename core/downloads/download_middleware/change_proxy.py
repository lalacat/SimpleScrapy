import logging
import random

logger = logging.getLogger(__name__)


class ChangeProxy(object):

    def __init__(self,logformatter,settings):
        self.lfm = logformatter
        self.settings = settings
        logger.info(*self.lfm.crawled(
            "DownloadMidder",self.__class__.__name__,
            '已初始化！！'
        ))
        self._proxies = self.settings['PROXY']
        self._proxy_flag = [True,False]

    @classmethod
    def from_crawler(cls,crawler):
        logformatter = crawler.logformatter
        settings = crawler.settings
        return cls(logformatter,settings)

    def process_request(self,request,spider):
        if hasattr(spider,'change_proxy'):
            if spider.change_proxy:
                if random.choice(self._proxy_flag):
                    proxy_config = random.choice(self._proxies)
                    request.meta['proxy_config'] = proxy_config

        return None