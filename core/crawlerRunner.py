import queue
import time
import logging

from queue import Empty

from twisted.internet import task, defer, reactor
from twisted.internet.defer import DeferredList, inlineCallbacks

from core.crawler import Crawler
from objectimport.loadobject import load_object
from settings import Setting
from utils.buildins import iter_dict
from utils.reactor import CallLaterOnce

logger = logging.getLogger(__name__)


class Slot(object):
    def __init__(self,logformatter,nextcall):
        self.lfm = logformatter
        self.closing = False
        self.heartbeat = task.LoopingCall(nextcall.schedule)
        self.nextcall = nextcall
        self.inprogress = list()

    def add_crawl(self,crawl):
        """
        记录正在进行的crawl
        :param crawl:
        :return:
        """
        # logger.debug("%s 添加到inprogress队列中" % crawl)
        self.inprogress.append(crawl)

    def remove_crawl(self,crawl):
        self.inprogress.remove(crawl)
        self._maybe_closing()

    def close(self):
        # logger.debug("关闭CrawlerRunner的slot")
        logger.debug(*self.lfm.crawled('CrawlerRunner','Slot',
                                        '已关闭'
                                       ))
        self.closing = defer.Deferred()
        self._maybe_closing()
        return self.closing

    def _maybe_closing(self):
        if self.closing and not self.inprogress:
            if self.nextcall:
                # logger.warning("CrawlerRunner的LoopCall已关闭")
                logger.debug(*self.lfm.crawled('CrawlerRunner', 'Slot',
                                               'LoopCall已关闭'
                                               ))
                self.nextcall.cancel()
                if self.heartbeat.running:
                    self.heartbeat.stop()
            self.closing.callback(None)


class CrawlerRunner(object):

    def __init__(self,tasks,settings=None,spidercls=None,name=None,logformat=None,middlewares=None):
        if isinstance(settings, dict) or settings is None:
            settings = Setting(settings)
        self.settings = settings
        self.middlewares = middlewares
        if logformat:
            self.lfm = logformat
        else:
            self.lfs = load_object(self.settings['LOG_FORMATTER_CLASS'])
            self.lfm = self.lfs.from_settings(self.settings)
        self.name = name if name else ''

        logger.info(*self.lfm.crawled(
            "CrawlerRunner", self.name,
            '已初始化')
                     )
        if isinstance(tasks,dict):
            self.tasks = iter_dict(tasks)
        else:
            self.tasks = tasks
        self.spider_loder = []
        # 装载的是Crawler的集合
        self._crawlers = set()
        # 装载的是defer的集合
        self._active = set()
        self._active_finish = False
        # 子爬虫的数量
        if self.name:
            self.MAX_CHILD_NUM = 4
        else:
            self.MAX_CHILD_NUM = 4
        # 子爬虫的名称
        # self.SPIDER_NAME_CHOICE = self.settings['SPIDER_NAME_CHOICE']
        self.SPIDER_NAME_CHOICE = False

        # 缓冲的地址最大数量
        # self.MAX_SCHEDULE_NUM = 10
        if spidercls:
            # 子爬虫的类
            self.spidercls = spidercls
        else :
            # 从设置中导入子爬虫的类
            self.spidercls = load_object(self.settings['SPIDER_CHILD_CLASS'])

        #  task完成标志位
        # self.filter_task = FilterTask(self.SPIDER_NAME_CHOICE)
        # 导入队列中任务个数的最大值
        self.filter_task = 10
        self._push_task_finish = False
        self._pull_task_finish = False
        self._next_task = None
        self.fifer = FilterTask(settings)

        self.slot = None
        self._closewait = None

        self.running = False
        self._pause = False
        self._task_schedule = queue.Queue()

    def crawl(self, *args, **kwargs):

        crawler = self._load_starturl_from_schedule()
        if crawler is None:
            return None
        return self._crawl(crawler, *args, **kwargs)

    def _crawl(self, crawler, *args, **kwargs):
        d = crawler.crawl(*args, **kwargs)
        self._crawlers.add(crawler.spider.name)

        def _done(result,d1):
            # 当已装载的爬虫运行完后，从列表中清除掉

            self._crawlers.discard(crawler.spider.name)
            self._active.discard(d1)
            logger.info(*self.lfm.crawled(
                "CrawlerRunner", self.name,
                '从队列中清除掉{0}'.format(crawler.spider.name))
                         )
            return result

        d.addBoth(_done,d)
        self._active.add(d)

    def _load_starturl_from_schedule(self):
        try:
            start_urls = self._task_schedule.get(block=False)
            name = start_urls[0]
            start_url = start_urls[1]
            # logger.debug("当前爬取的网页是:%s"%start_urls)
            logger.info(*self.lfm.crawled(
                "CrawlerRunner", self.name,
                '当前爬取的网页',start_url)
                         )
            crawler = Crawler(self.spidercls, self.settings,self.lfm,self,self.middlewares)
            crawler.create_spider_from_task(name,start_url)
            return crawler
        except Empty:
            logger.debug(*self.lfm.crawled(
                "CrawlerRunner", self.name,
                '队列中的task分配完毕')
                         )
            if not self._push_task_finish:
                self._create_task()
            else:
                self._pull_task_finish = True
        except Exception as e :
            logger.error(*self.lfm.error("CrawlerRunner",self.name,
                                         "",
                                         '出现错误:',),
                         extra=
                         {
                             'exception': e,
                         }, exc_info=True)
        return None

    def _create_task(self):
        logger.info(*self.lfm.crawled(
            "CrawlerRunner", self.name,
            'task装载入队列中')
                     )
        try:
            while self._task_schedule.qsize() <= self.filter_task:

                if self._next_task is None:
                    temp_cache = next(self._tasks)
                    self._next_task = self.fifer.filter_task(temp_cache)
                if isinstance(self._next_task,tuple):
                    filter_data = self._next_task
                    self._task_schedule.put(self._next_task)
                    self._next_task = None
                else:
                    try:
                        filter_data = next(self._next_task)
                        # filter_data = self.fifer.filter_task((name,temp_cache[name]))
                        if filter_data:
                            self._task_schedule.put(filter_data)
                    except StopIteration:
                        self._next_task = None
                logger.debug(*self.lfm.crawled(
                    "CrawlerRunner", 'schedule',
                    '载入队列',filter_data))
        except StopIteration:
            logger.debug(*self.lfm.crawled(
                "CrawlerRunner", self.name,
                'task载入完毕')
                         )
            self._tasks = None
            self._push_task_finish = True
        except ValueError as e:
            raise ValueError(e.args[0])

    @inlineCallbacks
    def start(self):
        try:
            self.init_task()
        except Exception as e:
            logger.error(*self.lfm.error("CrawlerRunner", "_create_task",
                                         '出现错误:',
                                         {
                                            'exception':e
                                         }))
        finally:
            self._closewait = defer.Deferred()
            self.delay_stop = reactor.callLater(1,self.stop,'cancel')
            yield self._closewait

    def init_task(self):
        assert not self.running,"task载入已启动"
        try:
            self.running = True
            logger.critical(*self.lfm.crawled('CrawlerRunner',self.name,'开始：%s' %time.strftime('%m/%d/%Y %H:%M:%S', time.localtime())))
                                              # {'time':time.strftime('%m/%d/%Y %H:%M:%S', time.localtime())}))

            # 将task导入到队列中
            self._tasks = make_generator(self.tasks)
            self._create_task()

            nextcall = CallLaterOnce(self.next_task_from_schedule)
            self.slot = Slot(self.lfm,nextcall)
            self.slot.nextcall.schedule()
            self.slot.heartbeat.start(5)

        except ValueError as e:
            raise ValueError(e)

    @inlineCallbacks
    def start_task(self):
        self._closewait = defer.Deferred()
        yield self._closewait

    @property
    def pause(self):
        return self._pause

    @pause.setter
    def pause(self,pause):
        if pause:
            if self._pause :
                logger.debug(*self.lfm.crawled('CrawlerRunner', self.name,
                                   '已经暂停了'))
            else:
                self._pause = True
        else:
            self._pause = False

    def needs_backout(self):
        flag = not self._pull_task_finish and len(self._active) < self.MAX_CHILD_NUM
        return flag

    @inlineCallbacks
    def next_task_from_schedule(self):

        if self._active_finish:
            logger.error(*self.lfm.crawled('CrawlerRunner', self.name,
                                           '正在执行的任务有：%s'%self._crawlers))
            return

        if self.pause:
            return

        if self.delay_stop.active():
            self.delay_stop.cancel()

        while self.needs_backout():
            self.crawl(self.spidercls)

        def change_falg(_):
            self._active_finish = False
            self.slot.nextcall.schedule()

            return None

        if self._active:
            self._active_finish = True
            logger.warning('即将激活的任务：%s'%self._crawlers)
            d = DeferredList(self._active)
            d.addBoth(change_falg)
            yield d

        if self.runner_is_idle():
            self.stop()

    def stop(self,reason='Finish'):
        assert self.running,'CrawlRunner 未启动'
        self.running = False
        if self.slot:
            self.slot.close()
            self.slot = None
        if self._closewait:
            self._closewait.callback("Finish")
        logger.critical(*self.lfm.crawled('CrawlerRunner', self.name,
                                'CrawlRunner停止,时间为:',
                                               {
                                                   'time':time.clock(),
                                                   'function':reason}
                                               ))
        self._push_task_finish = False
        self._pull_task_finish = False

    def runner_is_idle(self):
        if not self._push_task_finish:
            # 任务载入数据库完毕
            return False

        if not self._pull_task_finish:
            # 任务分配完毕
            return False

        if self._active:
            return False

        return True


class FilterTask(object):

    def __init__(self,settings= None):
        # 子爬虫的名称
        # self.SPIDER_NAME_CHOICE = settings['SPIDER_NAME_CHOICE']
        self.SPIDER_NAME_CHOICE = False
        self.name_num = 0
        # self.filter_words = settings['TASK_FILTER_NAME']
        self.filter_words = 'community_url'

    """
    传入的task类型有三种
    1.迭代前是list的列表，传入后，需要默认添加名称：SPIDER_NAME_CHOICE = Ture
    2.迭代前是数据的游标，传入后分两种，
        a)每个task中包含多个URL，此时数据库中每个对象的格式应该是dict类型{name:url}，此时name,url可以分别取task中的每个dict内容
        b)每个task中只含有一个URL，此时使用关键字就行，name需要使用默认添加名称
    """
    def filter_task(self,task):

        if isinstance(task, str) and not self.SPIDER_NAME_CHOICE:
            self.SPIDER_NAME_CHOICE = True
            # raise ValueError('爬虫的URL需要设置名称，或者将{SPIDER_NAME_CHOICE}设置为True,使用默认值！')
        if self.SPIDER_NAME_CHOICE:

            name = str(self.name_num)
            self.name_num += 1
            if isinstance(task, str):
                url = task
            else:
                if not isinstance(task, dict):
                    raise TypeError('task(%s)的类型必须是<str>或者包含关键字{%s}的<dict>，'
                                    '或者将{SPIDER_NAME_CHOICE}设置为False，自动为每个task设置名称'
                                    % (type(task), 'community_url'))
                else:
                    if task.get('community_url'):
                        url = task['community_url']
                    else:
                        raise KeyError('task(%s)包含关键字{%s}' % (type(task), 'community_url'))
        else:
            if isinstance(task, dict):
                if len(task) == 1:
                    name = [key for key in task.keys()][0]
                    url = [value for value in task.values()][0]
                elif len(task) > 1:
                    return make_generator(iter_dict(task))
                else:
                    raise TypeError('task(%s)的类型必须是<dict>，或者将{SPIDER_NAME_CHOICE}设置为True，自动为每个task设置名称' % type(task))
            else:
                if isinstance(task, tuple):
                    if task[0] == 'total_zone_name':
                        return None
                    name = task[0]
                    url = task[1]
        return (name, url)


def make_generator(tasks):
    try:
        it = iter(tasks)
    except Exception as e:
        raise TypeError('tasks不能被迭代')
    while True:
        try:
            yield it.__next__()
        except StopIteration:
            break



# a = {'1','2','3'}
# logger.error('列表%s' %a)