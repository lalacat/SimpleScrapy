import logging
import random

logger = logging.getLogger(__name__)


class ChangeRequestUserAgent(object):

    def __init__(self,crawler):
        self.lfm = crawler.logformatter
        logger.info(*self.lfm.crawled(
            "DownloadMidder",self.__class__.__name__,
            '已初始化！！'
        ))
        self._settings = crawler.settings
        self._headers = self._settings["HEADER_COLLECTION"]
        self.used_header = set()


    @classmethod
    def from_crawler(cls,crawler):
        return cls(crawler)

    def process_request(self,request,spider):
        if hasattr(spider,'change_header'):
            if spider.change_header:
                if request.meta.get('last_header'):
                    last_header = request.meta['last_header']
                    # new_header = Headers({'User-Agent':random.choice(self._headers)})
                    new_header = random.choice(self._headers)
                    while new_header == last_header:
                        new_header = random.choice(self._headers)
                        # self.used_header.add(new_header)
                else:
                    new_header = random.choice(self._headers)
                    request.meta['header_flag'] = new_header
                request.headers.setRawHeaders('User-Agent',new_header)
        return None


