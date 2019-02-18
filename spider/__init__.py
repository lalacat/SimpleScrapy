from utils.record_live_instances import object_ref
import logging

#logging.basicConfig(level=logging.DEBUG,format='%(asctime)s - %(filename)s[line:%(lineno)d] - %(levelname)s: %(message)s')


class BaseSpider(object):
    def __init__(self,**kwargs):
        self.name = type(self).__name__
        """将kwargs参数绑定到实例上，不会报错：AttributeError: 'BaseSpider' object has no attribute 'd'"""
        self.__dict__.update(kwargs)


class Spider(object_ref):
    name = None
    """真对部分爬虫有单独的用户设置，用户设置类型是["key1=value1","key2=value2"]"""
    custom_settings = None

    def __init__(self,name=None,**kwargs):
        if name is not None:
            self.name = name
        elif not getattr(self,"name",None):
            raise ValueError("自定义的%s 必须有个名字name" % type(self).__name__)
        self.__dict__.update(kwargs)
        if not hasattr(self,'start_urls'):
            self.start_urls = []
    @property
    def logger(self):
        logger = logging.getLogger(self.name)
        #  使用LoggerAdapter类来传递上下文信息到日志事件的信息中
        return logging.LoggerAdapter(logger,{"爬虫":self})

    def log(self,message,level=logging.DEBUG,**kw):

        self.logger.log(level,message,**kw)

    @classmethod
    def from_crawler(cls,crawler,*args,**kwargs):
        spider = cls(*args,**kwargs)
        spider._set_crawler(crawler)
        return spider

    @classmethod
    def update_settings(cls, settings):
        cls.settings = settings
        settings.setdict(cls.custom_settings or {}, priority='spider')

    @classmethod
    def from_schedule(cls,schedule):
        return cls(schedule)

    @classmethod
    def from_task(cls,crawler,spider_name,spider_start_urls,father_name):
        spider = cls()
        spider._set_crawler(crawler)
        spider._set_name(spider_name)
        spider._set_start_urls(spider_start_urls)
        spider._set_logformat(crawler.logformatter)
        spider._set_father_name(father_name)
        spider._set_build_time(crawler.build_time)
        return spider

    def _set_crawler(self,crawler):
        self.crawler = crawler

    def _set_name(self,name):
        self.name = name

    def _set_start_urls(self,start_urls):
        self.start_urls = start_urls

    def _set_logformat(self,logformat):
        self.lfm = logformat

    def _set_father_name(self,father_name):
        if father_name:
            self.father_name = father_name

    def _set_build_time(self,time):
        self.build_time = time

    def __str__(self):
        return '<%s %s>'%(self.name,self.start_urls)
    __repr__ = __str__


