import logging
from twisted.python.failure import Failure

from core.middleware import MiddlewareManager
from objectimport.bulid_component_list import bulid_component_list
from utils.defer import mustbe_deferred

logger = logging.getLogger(__name__)

def _isiterable(possible_iterator):
    return hasattr(possible_iterator, '__iter__')

class SpiderMiddlewareManager(MiddlewareManager):
    component_name = "Spider Middlerware"
    middlewares_name = 'SPIDER_MIDDLEWARES'
    @classmethod
    def _get_mwlist_from_settings(cls,settings):
        return bulid_component_list(settings[cls.middlewares_name],cls)

    def _add_middleware(self,mw):
        #  父类中含有加载open_spider,close_spider方法
        #  如果自定的中间件含有open_spider,close_spider需要通过父类的方法加载进去
        super(SpiderMiddlewareManager,self)._add_middleware(mw)
        if hasattr(mw,"process_spider_input"):
            self.methods["process_spider_input"].append(mw.process_spider_input)
        if hasattr(mw, 'process_spider_output'):
            self.methods['process_spider_output'].insert(0, mw.process_spider_output)
        if hasattr(mw, 'process_spider_exception'):
            self.methods['process_spider_exception'].insert(0, mw.process_spider_exception)
        if hasattr(mw, 'process_start_requests'):
            self.methods['process_start_requests'].insert(0, mw.process_start_requests)

    def scrape_response(self, scrape_func, response, request, spider):
        #  规范输出格式‘class.fun’
        fname = lambda f:'%s.%s' % (
                f.__self__.__class__.__name__,
                f.__name__)

        def process_spider_input(response):
            #  处理spider的内容，一般处理方法返回为None
            for method in self.methods['process_spider_input']:
                try:
                    result = method(response=response, spider=spider)
                    assert result is None, \
                        'Middleware %s must returns None or ' \
                        'raise an exception, got %s ' \
                        % (fname(method), type(result))
                except:
                    # 这步的目的是，如果request定义了errback，先经过errorback处理，再通过process_spider_exception处理
                    return scrape_func(Failure(), request, spider)
            return scrape_func(response, request, spider)

        def process_spider_exception(_failure):
            exception = _failure.value
            for method in self.methods['process_spider_exception']:
                result = method(response=response, exception=exception, spider=spider)
                assert result is None or _isiterable(result),\
                    'Middleware %s must returns None, or an iterable object, got %s ' % \
                    (fname(method), type(result))
                if result is not None:
                    return result
            return _failure

        def process_spider_output(result):
            for method in self.methods['process_spider_output']:
                result = method(response=response, result=result, spider=spider)
                # assert _isiterable(result), \
                #     'Middleware %s must returns an iterable object, got %s ' % \
                #     (fname(method), type(result))
            return result

        dfd = mustbe_deferred(process_spider_input, response)
        dfd.addErrback(process_spider_exception)
        dfd.addCallback(process_spider_output)
        return dfd

    def process_start_requests(self, start_requests, spider):
        return self._process_chain('process_start_requests', start_requests, spider)

