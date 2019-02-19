import logging
import pymongo

logger = logging.getLogger(__name__)


class HouseInfoDB(object):
    def __init__(self,crawler):
        self.lfm = crawler.logformatter
        logger.info(*self.lfm.crawled(
            'Pipe',self.__class__.__name__,
            '已初始化'
        ))
        self.settings = crawler.settings
        self.db_url = self.settings["MONGODB_URL"]
        self.db_name = self.settings["MONGODB_NAME_SOLD"]
        self.collection_name = None

        self.update_query = None
        self.update_doctument= None
        try:
            self.client = pymongo.MongoClient(self.db_url)
            self.db = self.client[self.db_name]
        except Exception as e:
            logger.error(*self.lfm.error("Pipe",self.__class__.__name__,
                                         '',
                          '出现错误:'),
             extra=
             {
                 'exception':e,
             })

    @classmethod
    def from_crawler(cls,crawler):
        return cls(crawler)

    def close_spider(self,spider):
        try:

            if not hasattr(spider, "sold_db"):
                logger.debug(*self.lfm.crawled(
                    "Spider", spider.name,
                    "没有设置数据库操作标志<handler_db>",
                    'self.__class__.__name__'))
                return None
            else:
                if spider.sold_db:
                    if hasattr(spider,'father_name'):
                        self.collection_name = spider.father_name
                    else:
                        return None
                    logger.info(*self.lfm.crawled(
                        "Spider", spider.name,
                        '正在添加进入数据库'))
                    item = dict()
                    item['community_name'] = spider.name
                    item.update(spider.result)
                    self._db_collection = self.db[self.collection_name]
                    if self.db_filter(item) == 'insert':
                        self._db_collection.insert_one(item)
                    elif self.db_filter(item) == 'update':
                        self._db_collection.update(self.update_query, self.update_doctument)
                    return None
                return None
        except Exception as e :
            print('close_spider'+e)
        self.db.logout()

    def db_filter(self,item):
        #  1.防止重复写入
        #  2.对某条字段更新
        exist = self._db_collection.find(item)
        update = self._db_collection.find({'community_name':item['community_name']})
        if exist.count() >= 1:
            #  爬到的对象未更新
            return 'exist'
        elif update.count() >= 1:
            old_item = update.next()
            self.update_query = {'community_name':old_item['community_name']}
            diff_key = item.keys()-old_item.keys()
            new_item = {key:item[key] for key in diff_key}
            if new_item is None:
                print(new_item)
            self.update_doctument ={'$set':new_item}
            return 'update'
        elif exist.count() == 0:
            return 'insert'

import zipfile


z = zipfile