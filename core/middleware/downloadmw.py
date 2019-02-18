import logging

from core.middleware import MiddlewareManager
from objectimport.bulid_component_list import bulid_component_list
from https.request import Request
from https.response import Response
from utils.defer import mustbe_deferred
from twisted.internet import defer

logger = logging.getLogger(__name__)


class DownloaderMiddlewareManager(MiddlewareManager):

    component_name = 'Downloader Middleware'
    middlewares_name = 'DOWNLOADER_MIDDLEWARE'

    @classmethod
    def _get_mwlist_from_settings(cls,settings):
        return bulid_component_list(settings[cls.middlewares_name],cls)

    def _add_middleware(self,mw):
        if hasattr(mw, 'process_request'):
            self.methods['process_request'].append(mw.process_request)
        if hasattr(mw, 'process_response'):
            self.methods['process_response'].insert(0, mw.process_response)
        if hasattr(mw, 'process_exception'):
            self.methods['process_exception'].insert(0, mw.process_exception)

    def download(self,download_func,request,spider):
        #  将默认处理的三个中间件分别添加到defer链上
        @defer.inlineCallbacks
        def process_request(request):
            #  处理process_request的方法自定义的时候，要么返回一个处理好的response要么返回一个None,
            #  返回一个request很容易陷入死循环。
            #  最大的作用就是处理request，往里添加或者修改内容的
            # logger.debug("Downloader Middleware: 加载process_request方法处理Request<%s>",request)
            logger.debug(*self.lfm.crawled(
                "Middleware", self.component_name,
                '加载process_request方法处理Request',
                request
            ))
            for method in self.methods['process_request']:
                response = yield method(request=request,spider =spider)
                assert response is None or isinstance(response,(Response,Request)),\
                'Downloader Middleware:%s.process_request 执行后返回的数据类型必须是<None>,<Response>,<Request>'\
                % method._class__._name__
                #  如果结果是下载后的，就直接返回
                if response:
                    defer.returnValue(response)
            #  如果参数是经过一系列中间件处理过的request，这一步就是对requset进行下载
            #  返回一个带有result的defer
            defer.returnValue((yield download_func(request=request,spider=spider)))

        @defer.inlineCallbacks
        def process_response(response):
            logger.debug(*self.lfm.crawled(
                    "Middleware", self.component_name,
                    '加载process_response方法处理Request',
                    request
            ))
            assert response is not None,"process_response接收到的数据是None"
            if isinstance(response,Request):
                defer.returnValue(response)

            for method in self.methods['process_response']:
                response = yield method(request=request, response=response,
                                        spider=spider)

                assert response is None or isinstance(response, (Response, Request)), \
                    'Downloader Middleware:%s.process_response 执行后返回的数据类型必须是<None>,<Response>,<Request>' \
                    % method._class__._name__
                if isinstance(response, Request):
                    defer.returnValue(response)
            defer.returnValue(response)

        @defer.inlineCallbacks
        def process_exception(_failure):
            # exception = _failure.value
            for method in self.methods['process_exception']:
                try:
                    method_name = method.__class__
                    response = yield method(request=request, exception=_failure,
                                            spider=spider)
                    assert response is None or isinstance(response, (Response, Request)), \
                        'Middleware %s.process_exception must return None, Response or Request, got %s' % \
                        (method_name, type(response))
                except Exception as e :
                    # raise TypeError("DownloadMW process_exception need 3 required positional arguments: 'request', 'exception', and 'spider' " )
                    raise e
                if response:
                    defer.returnValue(response)
            defer.returnValue(_failure)

        deferred = mustbe_deferred(process_request,request)
        deferred.addErrback(process_exception)
        deferred.addCallback(process_response)
        return deferred
