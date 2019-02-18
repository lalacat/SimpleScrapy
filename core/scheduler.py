import logging

import queue
logger = logging.getLogger(__name__)

class Scheduler(object):

    def __init__(self,mqclass=None):
        self.mqs = mqclass # 内存任务队列类FIFO

    @classmethod
    def from_crawler(cls,crawler=None):
        #setting = crawler.settings
        mqs = queue.Queue()
        cls.lfm = crawler.logformatter

        return cls(mqclass=mqs)

    def has_unhandler_requests(self):
        return len(self) > 0

    def open(self,spider):
        # logger.debug("Spider:%s 的Scheduler已打开"%spider.name)
        logger.debug(*self.lfm.crawled("Spider", spider.name,
                                       '已打开', 'Scheduler'))
        self.spider = spider
        #self.mqs = self._newfifo()
        return

    def next_request(self):
        logger.debug(*self.lfm.crawled("Spider",self.spider.name,
                                       '取下一个Request', 'Scheduler'))
        # 如果block为False，如果有空间中有可用数据，取出队列，否则立即抛出Empty异常
        try:
            requset = self.mqs.get(block=False)
        except Exception as e:
            # logger.debug("Spider:%s 的Scheduler数据已取完",self.spider.name)
            logger.debug(*self.lfm.crawled("Spider", self.spider.name,
                                           'Request已取完', 'Scheduler'))
            requset = None
        return requset

    def enqueue_request(self, request):
        try:
            self._mqpush(request)
        except Exception:
            return False
        return True

    def close(self,reason):
        # logger.debug(reason)
        logger.debug(*self.lfm.crawled("Spider", self.spider.name,
                                       'Scheduler已关闭'))
        return

    def _mqpush(self,requset):
        self.mqs.put(requset)

    def __len__(self):
        return self.mqs.qsize()

    def _newfifo(self):
        return self.mqclass



class RFPDupeFilter():
    pass