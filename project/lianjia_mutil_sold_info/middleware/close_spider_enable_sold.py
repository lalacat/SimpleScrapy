
from twisted.internet import defer

from core.crawlerRunner import CrawlerRunner
from project.lianjia_mutil_sold_info.spider.child_spider_sold_xpath import CollectSold

class Enable_Child_Spider(object):
    def __init__(self,settings):
        self.settings = settings

    @classmethod
    def from_crawler(cls,crawler):
        return cls(crawler)

    @defer.inlineCallbacks
    def close_spider(self,spider):
        try:
            if hasattr(spider,'output'):
                if spider.output:
                    if hasattr(spider,'sold_url'):
                        cr = CrawlerRunner(spider.sold_url, spider.settings, CollectSold, name=spider.name,
                                           logformat=spider.lfm, middlewares=spider.crawler.middlewares)
                        yield cr.start()
        except Exception as e :
            print("Spider_Out_print",e)

        yield None
