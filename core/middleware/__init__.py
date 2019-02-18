from collections import defaultdict
import logging
import pprint


from objectimport.loadobject import load_object
from utils.defer import process_parallel, process_chain, process_chain_both
logger = logging.getLogger(__name__)



class MiddlewareManager(object):
    """
    中间件的父类
    """
    component_name = 'Parent Middleware'

    def __init__(self,*middlewares):
        # logger.debug("MiddlewareManager:%s 已初始化..."%self.component_name)
        logger.debug(*self.lfm.crawled(
            "Middleware", self.component_name,
            '已初始化'
        ))
        self.clsnames = middlewares[0]
        self.middlewares = middlewares[1]

        self.methods = defaultdict(list)
        for name,mw in zip(self.clsnames,self.middlewares):
            self.methods[name].append(mw)
            self._add_middleware(mw)

    @classmethod
    #  子类实现该方法，从settings中获得方法，如果子类没呀重写该方法
    #  会报错
    def _get_mwlist_from_settings(cls,settings):
        raise NotImplementedError

    @classmethod
    def from_settings(cls,settings,crawler=None):
        """
        从default settings中加载默认的中间件
        :param settings:
        :param crawler:
        :return:
        """
        cls.lfm = crawler.logformatter
        try :
            mwlist = cls._get_mwlist_from_settings(settings)
            middlewares = []
            clsnames = []
            enabled = []
            for clspath in mwlist:
                try:
                    clsname = clspath.split('.')[-1]
                    mwcls = load_object(clspath)
                    #  两个if用来判断mwcls是类的情况下，是跟crawler关联还是和settings相关联
                    # 用来实例化所有的中间件
                    if crawler and hasattr(mwcls,'from_crawler'):
                        mw = mwcls.from_crawler(crawler)
                    elif hasattr(mwcls,'from_settings'):
                        mw = mwcls.from_settings(settings)
                    else:
                        mw = mwcls
                    middlewares.append(mw)
                    enabled.append(clspath)
                    clsnames.append(clsname)
                except Exception as e :
                    if e.args:
                        args = {'clsname': clsname, 'eargs': e.args[0]}
                        logger.warning(*cls.lfm.crawled(
                            "Middleware",cls.component_name,
                            '未生效:{clsname}: {eargs}'.format(**args))
                        )
            if len(middlewares) != len(clsnames):
                raise ImportError("中间件载入不完整")
            if middlewares and clsnames:
                # logger.info("生效%(componentname)ss的Middleware :\n%(enabledlist)s",
                #             {'componentname': cls.component_name,
                #              'enabledlist': pprint.pformat(enabled)},
                #             extra={'crawler': crawler})
                for mw in enabled:
                    logger.info(*cls.lfm.crawled(
                        "Middleware", cls.component_name,
                        '生效的中间件: %s' %mw))
            return cls(clsnames, middlewares)
        except Exception as e :
                logger.error(*cls.lfm.error(
                    "Middleware", cls.component_name,
                    function=None,
                    msg = e),
                exc_info = True)

    @classmethod
    def from_crawler(cls,crawler):
        return cls.from_settings(crawler.settings,crawler)

    def _add_middleware(self,mw):
        #  如果中间层添加有对spider进行处理的方法，应遵循后处理，先关闭的原则
        #  open:spider1->spider2->spider3
        #  close:spider3->spider2->spider1
        if hasattr(mw,"open_spider"):
            self.methods['open_spider'].append(mw.open_spider)
        if hasattr(mw,"close_spider"):
            self.methods['close_spider'].insert(0,mw.close_spider)

    def _process_parallel(self,methodname,obj,*args):
        return process_parallel(self.methods[methodname],obj,*args)

    def _process_chain(self,methodname,obj,*args):
        return process_chain(self.methods[methodname],obj,*args)

    def _process_chain_both(self, cb_methodname, eb_methodname, obj, *args):
        return process_chain_both(self.methods[cb_methodname],
            self.methods[eb_methodname], obj, *args)

    def open_spider(self, spider):
        return self._process_parallel('open_spider', spider)

    def close_spider(self, spider):
        return self._process_parallel('close_spider', spider)



