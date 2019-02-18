import logging
import time
from collections import deque, Iterable

import OpenSSL
from twisted.internet import defer
from twisted.internet.error import ConnectionLost, ConnectionDone, TCPTimedOutError
from twisted.python.failure import Failure
from twisted.web._newclient import ResponseNeverReceived

from https.request import Request
from https.response import Response
from core.item import BaseItem
from core.middleware.itempipelinemw import ItemPipelineManager
from core.middleware.spidermw import SpiderMiddlewareManager
from utils.defer import defer_result, defer_succeed, iter_errback, parallel
from utils.exception import CloseSpider

logger = logging.getLogger(__name__)


class Slot(object):
    """Scraper slot (one per running spider)"""

    MIN_RESPONSE_SIZE = 1024

    def __init__(self, max_active_size=5000000):
        self.max_active_size = max_active_size
        self.queue = deque()
        self.active = set()
        #  通过记active_size来判断是否需要等待request处理结束
        self.active_size = 0
        self.itemproc_size = 0
        self.closing = None

    def add_response_request(self, response, request):
        #  添加序列，记录处理的大小
        deferred = defer.Deferred()
        self.queue.append((response, request, deferred))
        if isinstance(response, Response):
            self.active_size += max(len(response.body), self.MIN_RESPONSE_SIZE)
        else:
            self.active_size += self.MIN_RESPONSE_SIZE
        return deferred

    def next_response_request_deferred(self):
        #  先进先出
        response, request, deferred = self.queue.popleft()
        self.active.add(request)
        return response, request, deferred

    def finish_response(self, response, request):
        self.active.remove(request)
        if isinstance(response, Response):
            self.active_size -= max(len(response.body), self.MIN_RESPONSE_SIZE)
        else:
            self.active_size -= self.MIN_RESPONSE_SIZE

    def is_idle(self):
        #  当set()或者deque()为空的时候，返回的是false
        return not (self.queue or self.active)

    def needs_backout(self):
        return self.active_size > self.max_active_size


class Scraper(object):

    def __init__(self,crawler):
        self.crawler = crawler
        self.lfm = crawler.logformatter
        logger.debug(*self.lfm.crawled("Spider", crawler.spider.name,
                                       '已初始化', 'Scraper'))
        self.slot = None
        self.settings = crawler.settings

        self.DOWNLOAD_TCP_TIMEOUT_MAX_TIMES = self.settings['DOWNLOAD_TCP_TIMEOUT_MAX_TIMES']
        self.DOWNLOAD_TIMEOUT_MAX_TIMES = self.settings['DOWNLOAD_TIMEOUT_MAX_TIMES']

        if crawler.middlewares.get('SpiderMiddlewareManager'):
            self.spidermw = crawler.middlewares['SpiderMiddlewareManager']
        else:
            self.spidermw = SpiderMiddlewareManager.from_crawler(crawler)
            crawler.middlewares['SpiderMiddlewareManager'] = self.spidermw

        if crawler.middlewares.get('ItemPipelineManager'):
            self.itemproc = crawler.middlewares['ItemPipelineManager']
        else:
            self.itemproc = ItemPipelineManager.from_crawler(crawler)
            crawler.middlewares['ItemPipelineManager'] = self.itemproc
        #  单次最多能处理最大的item的个数
        self.concurrent_items = crawler.settings.getint('CONCURRENT_ITEMS')
        self.crawler = crawler

        self.timeout_times = dict()
        self.tcp_timeout_times = dict()



    @defer.inlineCallbacks
    def open_spider(self,spider):
        # logger.debug("Spider:%s 的Scraper已打开"%spider.name)
        logger.debug(*self.lfm.crawled("Spider", spider.name,
                                       '已打开', 'Scraper'))
        self.slot = Slot()
        self.spider = spider
        yield self.itemproc.open_spider(spider)

    def close_spider(self, spider):
        # logger.info("关闭 %s 的Scraper！！"%spider.name)
        logger.warning(*self.lfm.crawled("Spider", spider.name,
                                       '已关闭', 'Scraper'))
        slot = self.slot
        slot.closing = defer.Deferred()
        #  对所有的itemproc进行并行关闭
        slot.closing.addCallback(self.itemproc.close_spider)
        self._check_if_closing(spider, slot)
        return slot.closing

    def is_idle(self):
        """Return True if there isn't any more spiders to process"""
        return not self.slot

    def _check_if_closing(self, spider, slot):
        if slot.closing and slot.is_idle():
            slot.closing.callback(spider)

    def enqueue_scrape(self, response, request, spider):
        self.start_time = time.clock()
        logger.info(*self.lfm.crawled("Spider", spider.name,
                                           'response加入队列时间',
                                           {
                                               'function':'Scraper',
                                               'time': time.clock()
                                           }))
        slot = self.slot
        dfd = slot.add_response_request(response, request)

        def finish_scraping(_):
            # defer接收的结果是 self._scrape返回的结果
            slot.finish_response(response, request)
            self._check_if_closing(spider, slot)
            self._scrape_next(spider, slot)
            return _

        dfd.addBoth(finish_scraping)
        self._scrape_next(spider, slot)
        return dfd

    def _scrape_next(self, spider, slot):
        while slot.queue:
            response, request, deferred = slot.next_response_request_deferred()
            self._scrape(response, request, spider).chainDeferred(deferred)

    def _scrape(self, response, request, spider):
        """Handle the downloaded response or failure through the spider
        callback/errback"""
        assert isinstance(response, (Response, Failure))
        #  如果结果没有出错的时候，先进行中间件的处理，然后执行在request中或者是spider中定义的callback或者是_parse来处理结果
        #  结果处理完后执行自定义的规则，将结果进行制定规则的输出
        dfd = self._scrape2(response, request, spider)  # returns spiders processed output
        dfd.addErrback(self.handle_spider_error, request,response, spider)
        dfd.addCallback(self.handle_spider_output, request, response, spider)
        return dfd

    def _scrape2(self, response_failure, request, spider):
        """Handle the different cases of request's result been a Response or a
        Failure"""
        if not isinstance(response_failure, Failure):
            # 对response进入spider，在spider中出现的异常，离开spider进行自定义的处理
            return self.spidermw.scrape_response(self.call_spider, response_failure, request, spider)
        else:
            # 针对download模块中出现的错误
            dfd = self.call_spider(response_failure, request, spider)
            return dfd

    def call_spider(self, response, request, spider):
        if isinstance(response,Response):
            response.request = request
        dfd = defer_result(response)
        #  这一步才是真正意义上的处理爬到的结果，之前的都是在过滤错误
        dfd.addCallbacks(request.callback, request.errback)
        return dfd

    def handle_spider_error(self, _failure, request, response, spider):
        # 接受来自Spider中的异常，也可能是下载的异常没有处理掉
        # 也能收到handle_spider_output中，spider返回结果迭代过程中出现的异常
        exc = _failure.value

        end_time = time.clock()

        if isinstance(exc,TimeoutError):
            if not self.timeout_times.get(str(request)):
                self.timeout_times[str(request)] = 1

            if self.timeout_times[str(request)] < self.DOWNLOAD_TIMEOUT_MAX_TIMES:
                logger.error(*self.lfm.error(
                    'Spider',self.spider.name,
                    '因下载超时，第%d次添加到下载队列中' % self.timeout_times[str(request)],
                {
                    'function': 'Scraper',
                    'request': request,
                }))
                request.meta['timeout_times'] = self.timeout_times[str(request)]
                self.crawler.engine.crawl(request=request, spider=spider)
                self.timeout_times[str(request)] += 1
                return None

            if self.timeout_times[str(request)] == self.DOWNLOAD_TIMEOUT_MAX_TIMES:
                logger.error(*self.lfm.crawled(
                    'Spider', self.spider.name,
                    '因下载超时，重新下载的次数超过最大重复下载次数%d,不再下载' % self.DOWNLOAD_TIMEOUT_MAX_TIMES,
                    {
                        'function': 'Scraper',
                        'request': request,
                    }))
        elif isinstance(exc, TCPTimedOutError):
            if not self.tcp_timeout_times.get(str(request)):
                logger.error(*self.lfm.error('Spider', self.spider.name,
                                             '来自Download模块的<TCPTimedOutError>异常: ',
                                             {
                                                 'function': 'Scraper',
                                                 'request': request,
                                                 'exception': str(exc),
                                             }),
                             extra={
                                 'time': '(详情在debug模式下查看)，错误时间为：{:6.3f}s'.format(end_time - self.start_time)
                             }, exc_info=False)
                self.tcp_timeout_times[str(request)] = 1

            if self.tcp_timeout_times[str(request)] < self.DOWNLOAD_TCP_TIMEOUT_MAX_TIMES:
                logger.error(*self.lfm.error(
                    'Spider',self.spider.name,
                    '因tcp连接超时，第%d次添加到下载队列中' % self.tcp_timeout_times[str(request)],
                {
                    'function': 'Scraper',
                    'request': request,
                }))
                request.meta['tcp_timeout_times'] = self.tcp_timeout_times[str(request)]
                self.crawler.engine.crawl(request=request, spider=spider)
                self.tcp_timeout_times[str(request)] += 1
                return None

            if self.tcp_timeout_times[str(request)] == self.DOWNLOAD_TCP_TIMEOUT_MAX_TIMES:
                logger.error(*self.lfm.crawled(
                    'Spider', self.spider.name,
                    '因tcp连接超时，重新下载的次数超过最大重复下载次数%d,不再下载' % self.DOWNLOAD_TCP_TIMEOUT_MAX_TIMES,
                    {
                        'function': 'Scraper',
                        'request': request,
                    }))
        elif isinstance(exc,ConnectionLost) :
            logger.error(*self.lfm.error('Spider', self.spider.name,
                                         '来自Download模块的<ConnectionLost>异常: ',
                                         {
                                             'function': 'Scraper',
                                             'request': request,
                                             'exception': str(exc),
                                         }),
                         extra={
                             'time': '(详情在debug模式下查看)，错误时间为：{:6.3f}s'.format(end_time - self.start_time)
                         }, exc_info=False)
        elif isinstance(exc,OpenSSL.SSL.Error):
            logger.error(*self.lfm.error('Spider', self.spider.name,
                                         '来自Download模块的<OpenSSL>异常: ',
                                         {
                                             'function': 'Scraper',
                                             'request': request.meta['proxy'],
                                             'exception': str(exc),
                                         }),
                         extra={
                             'time': '(详情在debug模式下查看)，错误时间为：{:6.3f}s'.format(end_time - self.start_time)
                         }, exc_info=False)
        elif isinstance(exc,ConnectionDone):
            logger.error(*self.lfm.error('Spider', self.spider.name,
                                         '来自Download模块的<ConnectionDone>异常: ',
                                         {
                                             'function': 'Scraper',
                                             'request': request,
                                             'exception': str(exc),
                                         }),
                         extra={
                             'time': '(详情在debug模式下查看)，错误时间为：{:6.3f}s'.format(end_time - self.start_time)
                         }, exc_info=False)
        elif isinstance(exc,ResponseNeverReceived):
            logger.error(*self.lfm.error('Spider', self.spider.name,
                                         '来自Download模块的<ResponseNeverReceived>异常: ',
                                         {
                                             'function': 'Scraper',
                                             'request': request,
                                             'exception': str(exc),
                                         }),
                         extra={
                             'time': '(详情在debug模式下查看)，错误时间为：{:6.3f}s'.format(end_time - self.start_time)
                         }, exc_info=False)

        else:
            if self.lfm.level is not 'DEBUG':
                logger.error(*self.lfm.error('Spider',self.spider.name,
                                             '来自Spider模块的异常: ',
                                             {
                                                 'function':'Scraper',
                                                 'request':request,
                                                 'exception': _failure,
                                             }),
                             extra={
                                'time':'(详情在debug模式下查看)，错误时间为：{:6.3f}s'.format(end_time-self.start_time)
                            },exc_info = True)

            else:
                logger.error(*self.lfm.error('Spider',self.spider.name,
                                             '来自Spider或者Download模块的异常，详细内容为:',
                                             {
                                                 'function':'Scraper',
                                                 'request':request,
                                                 'exception': _failure,
                                             }),
                             extra={
                                'time':'错误时间为：{:6.3f}s'.format(end_time-self.start_time)
                            },exc_info = True)

        if isinstance(exc,CloseSpider):
            self.crawler.engine.close_spider(spider,exc or "cancelled")
        return None

    def handle_spider_output(self, result, request, response, spider):
        """
        通过spider._parse或者request.callback处理后的数据，可能会根据需要，返回None或者Request，可迭代型的list,dict,或者是yield 生成器
        其中生成器是无法测定具体的大小的，所以不能用len()来确定并行处理task的数目
        并行处理task的数目100和20的区别并不大

        :param result:
        :param request:
        :param response:
        :param spider:
        :return:
        """
        if not result:
            logger.info(*self.lfm.crawled('Spider',spider.name,
                                             '返回的结果为<None>,不经过自定义{process_item}处理',
                                             '_parse(callback)'
                                             ))
            return defer_succeed(None)
        if isinstance(result,Request):
            #  针对是return 当spider处理后的结果是yield，那么result的类型是generator
            self.crawler.engine.crawl(request=result, spider=spider)
            return defer_succeed(result)
        if not isinstance(result,Iterable):
            # logger.warning("%s._parse或者request.callback处理的结果不是<Iterable>，而是%s类型的数据,不能通过pipe处理！！"%(spider.name,type(result)))
            logger.info(*self.lfm.crawled('Spider', spider.name,
                                             '_parse(callback)',
                                             '处理的结果是{1}类型,不是<Iterable>,不能经过自定义<pipe>处理'.format(type(result))))
            return defer_succeed(result)
        #  将自定义处理好的结果，通过这个方法并行执行自定义的rule（pipe process_item）
        #  这里的结果默认是能够迭代的List或者是dict类型的结果，每个结果都是并列的，能够同时符合process_item处理规则
        #  其中list里的结果是两种类型，一种是BaseItem及其子类一种是dict类型，这些都是在request或者spider中自己
        #  处理后的得到的
        # logger.debug("%s的parse处理后的结果类型是%s,下一步进行process_item并行处理"%(spider.name,type(result)))
        logger.debug(*self.lfm.crawled('Spider', spider.name,
                                         '_parse(callback)',
                                         '处理后的结果类型是{0},下一步进行process_item并行处理'.format(type(result))))
        it = iter_errback(result, self.handle_spider_error, request, response, spider)

        dfd = parallel(it,self.concurrent_items,self._process_spidermw_output, request, response, spider)
        dfd.addCallback(self._process_item_time)
        return dfd

    def _process_spidermw_output(self, output, request, response, spider):
        """Process each Request/Item (given in the output parameter) returned
        from the given spider
        """
        logger.debug(*self.lfm.crawled("Spider", spider.name,
                               '并行处理中',
                               {
                                   'function': 'Scraper',
                                   'request': request
                               }))
        # spider.parse返回的是yield的时候，解开生成器在这里完成
        if isinstance(output, Request):
            logger.info(*self.lfm.crawled('Spider',spider.name,
                                               'Output的类型是<Request>,将添加到下载队列中,加入时间:',
                                               {
                                                   'function':output,
                                                   'time':time.clock()
                                               }))
            self.crawler.engine.crawl(request=output, spider=spider)
        elif isinstance(output, (BaseItem, dict,int)):
            # logger.info("处理的output%(request)s的类型是<BaseItem, dict,int>，
            # 将由自定义的process_item方法进行处理！！添加时间是：%(time)f",
            # {"request":output,"time":time.clock()})
            logger.info(*self.lfm.crawled(
                'Spider',spider.name,
                'Output的类型是<BaseItem, dict,int>,将通过自定义的process_item方法进行处理,处理时间:',
                {
                    'time':time.clock()
                }
            ))

            self.slot.itemproc_size += 1
            dfd = self.itemproc.process_item(item=output,spider=spider)
            dfd.addBoth(self._itemproc_finished, output, response, spider)

            return dfd

        elif output is None:
            pass

        else:
            typename = type(output).__name__
            # logger.error('Spider must return Request, BaseItem, dict or None, '
            #              'got %(typename)r in %(request)s',
            #              {'request': request, 'typename': typename},
            #              extra={'spider': spider})
            logger.error(*self.lfm.error('Spider',spider.name,
                                         '处理的结果的类型必须是<Request>,<BaseItem>,<dict>,<None>。返回的类型是:',
                                       {
                                           'function':'Scraper',
                                           'request':request,
                                           'exception': typename
                                       }))

    def _itemproc_finished(self, output, item, response, spider):
        """ItemProcessor finished for the given ``item`` and returned ``output``
        """
        #  得到的output是一个处理过的items，一般是dict类型的数据
        #  output==item

        self.slot.itemproc_size -= 1
        if isinstance(output, Failure):

            # logging.error(ex)
            # logger.error('process item(%(item)s)过程中出现错误', {'item': item})
            logger.error(*self.lfm.error('Spider',spider.name,
                                         '处理过程中出现错误:',
                                       {
                                           'function':'Scraper',
                                           'request':'item',
                                           'exception': output
                                       }))
        else:
            logger.debug(*self.lfm.crawled('Spider',spider.name,'处理完毕',
                                           {
                                               'function': 'Scraper',
                                               'request': 'item'
                                           }),exc_info=True)
        return None

    def _process_item_time(self,_):
        end_time = time.clock()
        logger.debug(*self.lfm.crawled("Spider",self.spider.name,
                            'process_item处理完毕后的时间:',
                                            {
                                                'time':end_time,
                                                'function':"Scraper"
                                            }
                                            ))
        logger.debug(*self.lfm.crawled("Spider", self.spider.name,
                                       "完成Scraper模块使用了",
                                       {
                                           'time': end_time - self.start_time,
                                           'function': "Scraper"
                                       }))

        return None