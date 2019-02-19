from twisted.internet import defer, task
from twisted.python.failure import Failure
from https.request import Request
from https.response import Response
from core.scraper import Scraper
from utils.reactor import CallLaterOnce
from objectimport.loadobject import load_object
import logging,time


logger = logging.getLogger(__name__)


class Slot(object):
    """
    爬虫过程中，爬虫引擎的插槽
    """
    def __init__(self,logformatter,start_requests,close_if_idle,nextcall,scheduler):
        """

        :param start_requests: 获取Spider中的爬虫网站
        :param close_if_idle:
        :param nextcall:
        :param scheduler:
        """
        self.lfm = logformatter
        logger.debug(*self.lfm.crawled("Engine","Slot",'已初始化'))

        self.closing = False
        self.inprogress = list() #存放正在爬虫的网站,保证每个defer都执行完
        self.start_requests = start_requests
        self.close_if_idle = close_if_idle
        self.nextcall = nextcall
        self.scheduler = scheduler
        # 不断调用方法，通过start和stop控制调用的启停
        self.heartbeat = task.LoopingCall(nextcall.schedule)

    def add_request(self, request):
        """
        :param request:
        :return:
        """
        # logger.debug("Engine:Slot <%s> 添加到inprogress中"%request)
        logger.debug(*self.lfm.crawled("Engine",'Slot','添加到inprogress中',request))
        self.inprogress.append(request)

    def remove_request(self, request,name):
        #  当request处理完后就可以移除掉了
        self.inprogress.remove(request)
        self._maybe_fire_closing(name)

    def close(self,name):
        # logger.info("关闭 %s 的 slot！！"%name)

        logger.info(*self.lfm.crawled("Spider",name,'Engine的Slot关闭'))
        self.closing = defer.Deferred()
        self._maybe_fire_closing(name)
        return self.closing

    def _maybe_fire_closing(self,name):
        """
        当执行close方法后，self.closing不为False，而且要保证在执行的爬虫任务都要完成的情况下，
        才能够停止心跳函数
        :return:
        """
        if self.closing and not self.inprogress:
            if self.nextcall:
                # logger.warning("%s 的LoopCall已关闭"%name)
                logger.info(*self.lfm.crawled("Spider",name,'Engine的Slot.LoopCall已关闭'))
                self.nextcall.cancel()
                if self.heartbeat.running:
                    self.heartbeat.stop()
            self.closing.callback(None)


class ExecutionEngine(object):
    """
    引擎：所有调度
    """

    def __init__(self,crawler,spider_closed_callback):
        # 获取log的格式
        self.lfm = crawler.logformatter
        # logger.debug("Engine 已初始化")
        logger.debug(*self.lfm.crawled("Spider",crawler.spider.name,
                                               '已初始化','Engine'))
        self.crawler =crawler
        self.settings = crawler.settings

        self.slot = None
        self.spider = None
        self.running = False
        self.paused = False
        self.engine_name = None
        self.start_time = None
        self._closewait = None

        # 从settings中找到Scheduler调度器，找到Scheduler类
        self.scheduler_cls = load_object(self.settings["SCHEDULER"])
        # 同样，找到Downloader下载器类
        downloader_cls = load_object(self.settings["DOWNLOADER"])
        self.downloader = downloader_cls(crawler)
        self.scraper = Scraper(crawler)
        self.crawlling = []
        self._spider_closed_callback = spider_closed_callback

        self.flag = False

    @defer.inlineCallbacks
    #  将爬虫中的网页读取出来
    def open_spider(self,spider,start_requests,close_if_idle=True):
        # logger.info("Spider:%s 的Engine已打开"%spider.name)
        logger.info(*self.lfm.crawled("Spider", spider.name,
                                       '已打开', 'Engine'))
        assert self.has_capacity(),"此引擎已经在处理爬虫了，所以不能处理%s %r" %\
            spider.name
        self.engine_name = spider.name + '\'s engine'
        # 将_next_request注册到reactor循环圈中，便于slot中loopCall不断的调用
        #  相当于不断调用_next_request(spider)
        try:
            nextcall = CallLaterOnce(self._next_request,spider)
            #  初始化scheduler
            scheduler = self.scheduler_cls.from_crawler(self.crawler)
            #  调用中间件，就是添加若干个inner_derfer
            start_requests = yield self.scraper.spidermw.process_start_requests(start_requests,spider)
            self.spider = spider
            #  封装Slot对象
            slot = Slot(self.lfm,start_requests,close_if_idle,nextcall,scheduler)
            self.slot = slot
            # 调用scheduler的open
            yield scheduler.open(spider)
            #  调用scraper的open
            yield self.scraper.open_spider(spider)
            #  启动页面读取，进行爬虫工作
            slot.nextcall.schedule()
            #  自动调用启动，每5秒一次调用
            slot.heartbeat.start(5)
        except Exception as e:
            logger.error(*self.lfm.error("Spider",spider.name,
                         "Open Spider过程中出现错误：",
                                         {
                                             'function':'Engine',
                                             'exception':e
                                         }),
                         exc_info = True)
            raise Exception('来自Engine的报错:%s')

    @defer.inlineCallbacks
    def start(self):
        # running为Flase的时候，不报错，为True的时候，报错
        assert not self.running,"%s Engine已启动"%self.spider.name
        self.running = True
        engine_start_time = time.clock()
        # logger.warning("%s Engine开始,时间:[%6.3f]s..." %(self.spider.name,engine_start_time))
        logger.warning(*self.lfm.crawled("Spider", self.spider.name,
                        '开始时间',
                       {
                        'function':'Engine',
                        'time':engine_start_time
                        }))

        self._closewait = defer.Deferred()
        self._closewait.addBoth(self._finish_stopping_engine)
        yield self._closewait

    def stop(self):
        # assert self.running,"引擎没有运行"
        self.running = False
        if self._closewait:
            self._closewait.callback(None)
        return True

    def _finish_stopping_engine(self,_):
        end_time = time.clock()
        # logger.warning("%s Engine关闭,运行时间:[%7.6f]s...",self.engine_name,end_time)
        logger.warning(*self.lfm.crawled("Spider", 'Engine',
                                              '关闭时间', {'time':end_time} ))
        return None

    def pause(self):
        """
        Pause the execution engine
        此时循环还在进行中，只不过限制了_next_request进行下一步操作
        """
        self.paused = True

    def unpause(self):
        """Resume the execution engine"""
        self.paused = False

    def _next_request(self,spider):
        """
        爬虫爬网页的主要运行方法
        首先是判断slot和引擎的状态，
        其次是通过scheduler对队列中的request进行下载
        最后才是通过start_requset不断将request添加到scheduler中去
        scheduler队列中的request保持在一个，只有下载结束了才会去取新的一个
        :param spider:
        :return:
        """
        # logger.debug("Spdier:%s 调用[_next_request]...",spider.name)

        slot = self.slot
        if not slot:
            return

        if self.paused:
            return
        logger.info(*self.lfm.crawled("Spider", spider.name,
                                       '调用[_next_request],还剩下:{:d}个任务'.format(len(slot.inprogress)), 'Engine'))
        # 是否等待，因为在opeb_spider中通过nextcall中的LoopCall不断的调用
        # _next_requset必须设置flag来保障，每次调用的时候只有前一次的处理结束
        # 后才能继续执行新的任务
        while not self._needs_backout():
            # 从scheduler中获取request
            # 注意：第一次获取时，是没有的，也就是会break出来从而执行下面的逻辑
            # 当scheduler的request队列为空后，就break
            if not self._next_request_from_scheduler(spider):
                break

        # 如果start_requests有数据且不需要等待
        if slot.start_requests and not self._needs_backout():
            try:
                request = next(slot.start_requests)
            except StopIteration:
                slot.start_requests = None
            except Exception as e :
                slot.start_requests = None
                logger.error(*self.lfm.error("Spider",spider.name,
                                     "获取start_requests过程中出现错误：",
                                     {
                                         'function': 'Engine',
                                         'exception': e
                                     }))
            #  没有发生异常执行此段代码
            else:
                self.crawl(request, spider)

        if self.spider_is_idle() and slot.close_if_idle:
           self._spider_idle(spider)

    def _needs_backout(self):
        slot = self.slot
        """
        判断爬虫的状态判断是否需要等待：
        只要有一个False返回False,全True返回True
        1.引擎是否正在运行,默认是False，执行完start后为True
        2.slot是否关闭了,默认slot.closing是False
        3.downloader下载超过预设默认是16个，同时下载的页面超过16个就返回ture
        4.scraper处理response超过预设
        """
        return not self.running \
            or slot.closing \
            or self.downloader.needs_backout() \
            or self.scraper.slot.needs_backout()

    def _next_request_from_scheduler(self,spider):
        #  从scheduler队列中获取request
        #  并进行下载
        slot = self.slot
        request = slot.scheduler.next_request()
        if not request:
            return

        def remove_request(_,slot,request,spider):
            slot.remove_request(request, spider.name)
            # logger.info("remove_request:%s,inprogress中还剩下%d个任务"%(request,len(slot.inprogress)))
            logger.info(*self.lfm.crawled("Spider", spider.name,
                                          'inprogress中还剩下:{:d}个任务'.format(len(slot.inprogress)),
                                          'Engine'))
            return _

        def next_slot(_,slot):
            # logger.debug("next_slot")
            logger.debug(*self.lfm.crawled("Spider", spider.name,
                                          '调用[next_slot]', 'Engine'))
            slot.nextcall.schedule()
            return _

        def log_error(_,msg):
            error_msg = _.value if isinstance(_,Failure) else _
            logger.error(*self.error('Spider',spider.name,
                                     msg,
                                     {
                                         'function':'Engine',
                                         'request':request,
                                         'exception': error_msg
                                     }))

        d = self._download(request,spider)

        d.addBoth(self._handle_downloader_output,request,spider)
        # d.addErrback(lambda f: logger.info('Error while handling downloader output',extra={'spider': spider}))
        d.addErrback(log_error,'经过Scrapy处理后，出现错误:')

        #  移除掉处理过的request
        d.addBoth(remove_request,slot,request,spider)
        # d.addErrback(lambda f: logger.info('Error while scheduling new request',extra={'spider': spider}))
        d.addErrback(log_error,"在移除已处理的request时出现错误:")

        #  进行下一次的处理request
        d.addBoth(next_slot,slot)
        # d.addErrback(lambda f: logger.info('Error while scheduling new request',extra={'spider': spider}))
        d.addErrback(log_error,"在添加新request进入scheduler时出现错误")
        return d

    def _handle_downloader_output(self,response,request,spider):
        #  得到的是下载后的结果，此方法是将结果输出到其他需要处理结果的地方
        # logger.debug("处理%s的下载结果"%request)
        logger.debug(*self.lfm.crawled("Spider", spider.name,
                                       '开始处理下载的结果', request))
        assert isinstance(response, (Request, Response, Failure)), response
        if isinstance(response, Request):
            #  到这一步得到的response还是Request类，表明下载不成功，
            #  需要重新走一遍流程
            self.crawl(response, spider)
            return
        # 进入到scraper中进行output的处理
        d = self.scraper.enqueue_scrape(response,request,spider)
        return d

    def spider_is_idle(self):
        if not self.scraper.slot.is_idle():
            #  scraper的slot是否为None
            return False

        if self.downloader.active:
            #  判断active队列是否为空，不为空就返回False
            return False

        if self.slot.start_requests is not None:
            return False

        if self.slot.scheduler.has_unhandler_requests():
            return False

        return True

    def _download(self,request,spider):

        slot = self.slot
        #  将取得的requst添加到in_progress中
        slot.add_request(request)

        def _on_success(response):
            #  若下载成功，得到的是response数据，则就返回response
            assert isinstance(response,(Response,Request)),"返回的不是Response or Request类型的数据，而是%s"%type(response)
            if isinstance(response,Response):
                logger.debug(*self.lfm.crawled("Spider", spider.name,
                                               '下载成功', request))
                # response.request = request
            return response

        def _on_complete(_):
            #  当一个requset处理完后，就进行下一个处理
            slot.nextcall.schedule()
            return _

        dwld = self.downloader.fetch(request,spider)
        dwld.addCallback(_on_success)
        dwld.addBoth(_on_complete)
        return dwld

    @property
    def open_spiders(self):
        return [self.spider] if self.spider else []

    def crawl(self, request, spider):
        assert spider in self.open_spiders, \
            "Spider %r not opened when crawling: %s，即%r 没有执行open_spider方法" % (spider.name, request,spider.name)
        #  添加到队列中去
        self.schedule(request, spider)
        self.slot.nextcall.schedule()

    def has_capacity(self):
        """保证一个engine对应对应处理一个spider,一个slot对应一个spider"""
        return not bool(self.slot)

    def schedule(self, request, spider):
        # logger.debug("Spider:%s <%s>添加到Scheduler中成功..." ,spider.name,request)
        logger.debug(*self.lfm.crawled("Spider", spider.name,
                                       '添加到Scheduler中成功',request))
        if not self.slot.scheduler.enqueue_request(request):
            logger.error(*self.lfm.error("Spider", spider.name,
                                           '添加到Scheduler中失败',request))

    def _spider_idle(self,spider):
        if self.spider_is_idle():
            self.close_spider(spider,reason="finished")

    def close_spider(self,spider,reason='cancelled'):
        """关闭所有的爬虫和未解决的requests"""
        slot = self.slot
        if slot.closing:
            # 不是False，就是Defferred对象，就表明已经关闭了
            return slot.closing
        dfd = slot.close(spider.name)

        def log_failure(_,msg):
            error_msg = _.value if isinstance(_,Failure) else _
            logger.error(*self.error('Spider', spider.name,
                                     msg,
                                     {
                                         'function':'Engine',
                                         'exception': error_msg
                                     }))
            return _

        #  关闭下载器
        dfd.addBoth(lambda _: self.downloader.close())
        dfd.addErrback(log_failure,'Downloader 关闭失败')

        # 关闭scraper
        dfd.addBoth(lambda _: self.scraper.close_spider(spider))
        dfd.addErrback(log_failure,'Scraper 关闭失败')

        #  关闭scheduler
        dfd.addBoth(lambda _: slot.scheduler.close(reason))
        dfd.addErrback(log_failure,'Scheduler 关闭失败')

        dfd.addBoth(lambda _:logger.warning(*self.lfm.crawled("Spider", spider.name,
                                       '关闭时间:',
                                        {
                                         'function': 'Spider',
                                         'request' : '{'+reason+'}',
                                         'time': time.clock()
                                        })))

        #  引擎中的slot清空
        dfd.addBoth(lambda _: setattr(self, 'slot', None))
        dfd.addErrback(log_failure,'释放Slot的时候出现错误:')

        # 引擎中的spider清空
        dfd.addBoth(lambda _: setattr(self, 'spider', None))
        dfd.addErrback(log_failure,'释放Spider的时候出现错误:')

        dfd.addBoth(lambda _: self._spider_closed_callback(spider))

        return dfd

    def _close_all_spider(self):
        dfds = [self.close_spider(s, reason='shutdown') for s in self.open_spiders]
        dlist = defer.DeferredList(dfds)
        return dlist

