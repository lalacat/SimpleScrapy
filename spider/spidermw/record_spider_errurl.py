import logging

from twisted.python.failure import Failure

logger = logging.getLogger(__name__)


class RecordSpiderErrorUrl(object):

    def __init__(self,crawler):
        self.lfm = crawler.logformatter
        logger.info(*self.lfm.crawled(
            "SpiderMiddleware",self.__class__.__name__,
            '已初始化！！'
        ))
        self._settings = crawler.settings


    @classmethod
    def from_crawler(cls,crawler):
        return cls(crawler)

    def process_spider_input(self,response,spider):
        spider.name = 'test'
        if hasattr(spider,'request_headers'):
            print('true')
        else:
            print('false')
        return None

    def process_spider_exception(self,response,exception,spider):
        print(response)
        if isinstance(response,Failure):
            logger.critical('%s处理时出现错误,错误的原因是%s' % (spider.name, exception))
        return None

    def process_spider_output(self,response,result,spider):
        print(result)
        print(spider.request_headers)
        return None