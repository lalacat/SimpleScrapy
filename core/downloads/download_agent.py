from twisted.web.client import Agent,ResponseDone,ResponseFailed, \
    HTTPConnectionPool
from twisted.web.http import _DataLoss, PotentialDataLoss
from twisted.internet import reactor,defer
from twisted.internet.ssl import ClientContextFactory
from twisted.web.iweb import IBodyProducer,UNKNOWN_LENGTH
from twisted.internet.protocol import Protocol

from io import BytesIO
from urllib.parse import urldefrag
from zope.interface import implementer
import time, logging
from https.parse_url import to_bytes
from https.response import Response

logger = logging.getLogger(__name__)


class DownloaderClientContextFactory(ClientContextFactory):
    """用于Https验证"""
    def getContext(self,host=None,port=None):
        return ClientContextFactory.getContext(self)


class HTTPDownloadHandler(object):

    def __init__(self,logformatter,settings):
        # 管理连接的，作用request完成后，connections不会自动关闭，而是保持在缓存中，再次被利用
        self.lfm = logformatter
        logger.debug(*self.lfm.crawled(
            'Downloader',
            'HTTPDownloadHandler',
            '已初始化'
        ))
        self._pool = HTTPConnectionPool(reactor,persistent=True)
        self._pool.maxPersistentPerHost = settings.getint('CONCURRENT_REQUESTS_PER_DOMAIN')
        self._pool._factory.noisy = False # 用于设置proxy代理

        self._contextFactory = DownloaderClientContextFactory()

        self._default_maxsize = settings.getint('DOWNLOAD_MAXSIZE')
        self._default_warnsize = settings.getint('DOWNLOAD_WARNSIZE')
        self._fail_on_dataloss = settings.getbool('DOWNLOAD_FAIL_ON_DATALOSS')
        self._disconnect_timeout = 1

    @classmethod
    def from_crawler(cls,crawler):
        return cls(crawler.logformatter,crawler.settings)

    def download_request(self,request,spider):
        """返回一个http download 的 defer"""
        self.spider = spider
        agent = DownloadAgent(contextFactory=self._contextFactory,pool=self._pool,
                              maxsize=getattr(spider,'download_maxsize',self._default_maxsize),
                              warnsize=getattr(spider,'download_warnsize',self._default_warnsize),
                              fail_on_dataloss=self._fail_on_dataloss,logformatter = self.lfm
                              )
        return agent.download_request(request)

    def close(self):
        #  关闭所有的永久连接，并将它们移除pool 返回是一个defer
        d = self._pool.closeCachedConnections()
        #  直接关闭closeCachedConnections会引起网络或者服务器端的问题，所以，通过人工设置延迟
        #  来激发defer,closeCachedConnections不能直接处理额外的errbacks，所以需要个人设定一个
        #  callback在_disconnect_timeout之后
        logger.warning(
            *self.lfm.crawled(
                'Downloader',
                'HTTPDownloadHandler',
                '已关闭'
        ))
        delayed_call = reactor.callLater(self._disconnect_timeout,d.callback,[])

        #  判断cancel_delayed_call是否在等待，True就是出于激活状态,还没被执行
        #  False代表着已经被激活或者已经被取消了
        def cancel_delayed_call(result):
            if delayed_call.active():
                delayed_call.cancel()
            return result

        d.addBoth(cancel_delayed_call)
        return d


class DownloadAgent(object):
    _Agent = Agent

    def __init__(self,contextFactory=None, connectTimeout=10, bindAddress=None,
                 pool=None,maxsize=0,warnsize=0,fail_on_dataloss=False,logformatter=None):
        self.lfm = logformatter
        logger.debug(*self.lfm.crawled(
            'HTTPDownloadHandler',
            'DownloadAgent',
            '已初始化'
        ))
        self._contextFactory = contextFactory
        self._connectTimeout = connectTimeout
        self._bindAddress = bindAddress
        self._pool = pool
        self._transferdata = None
        self._maxsize = maxsize # 规定最大的下载信息，防止下载的网页内容过大，占资源
        self._warnsize = warnsize# 给下载的网页设置一个警戒线
        self._fail_on_dataloss = fail_on_dataloss

    def _getAgent(self,timeout):

        return self._Agent(reactor,contextFactory=self._contextFactory,
                           connectTimeout=timeout,
                           bindAddress=self._bindAddress,
                           pool=self._pool)

    def download_request(self,request):
        timeout = request.meta.get('download_timeout') or self._connectTimeout
        delay_time = request.meta.get('delay_time')
        logger.error(*self.lfm.crawled("Request", request,
                                       '正在下载,延迟了%6.3f' %delay_time, ))
        agent = self._getAgent(timeout)
        #  url格式如下：protocol :// hostname[:port] / path / [;parameters][?query]#fragment
        #  urldefrag去掉fragment
        url = urldefrag(request.url)[0]
        method = to_bytes(request.method)
        headers = request.headers
        self.request = request

        if request.body:
            bodyproducer = _RequestBodyProducer(request.body)
        elif method == b'POST':
            bodyproducer = _RequestBodyProducer(b'')
        else :
            bodyproducer = None
        start_time = time.time()

        d = agent.request(method,
              to_bytes(url),
              headers,
              bodyproducer)
        d.addCallback(self._cb_latency,request,start_time)
        try:
            #  下载request.body
            d.addCallback(self._cb_body_get,request)
            d.addCallback(self._cb_body_done,request,url)
            #  检查是否超时，如果在设定时间还没返回结果，就将defer取消
            #  当d.callback执行的方法，一直处于占用状态的时候，callLater是不会执行的，
            #  只有执行的方法是能够回到reactor主循环的时候，callLater才能执行
            #  _RequestBodyProducer中dataReceived方法不会一直占用，数据还没接收到是，是会回到reactor循环的，
            #  当总的接收数据的时间超过了timeout的时候，才会执行d.cancel
            self._timeout_cl = reactor.callLater(timeout,d.cancel)
            d.addBoth(self._cb_timeout,url,timeout)
        except Exception as e:
            # logger.error(e)
            logger.error(*self.lfm.error("Request", request,
                                        DownloadAgent,
                                        '下载过程中出现错误:'),
                         extra=
                         {
                             'exception': e,
                         }, exc_info=True)

        return d

    def _cb_latency(self,result,request, start_time):
        """记录延迟时间"""
        request.meta['download_latency'] = time.clock() - start_time
        #logger.debug("记录延迟时间 %d " %request.meta['download_latency'])
        return result

    def _cb_timeout(self,result,url,timeout):
        # logger.debug("进入下载超时处理方法")
        logger.debug(*self.lfm.crawled(
                    'Request',
                    self.request,
                    '判断是否下载超时')
                     )
        # 如果_timeout_cl还没触发，就取消掉，不用再延迟了
        if self._timeout_cl.active():
            # logger.debug("下载没有超时")
            logger.debug(*self.lfm.crawled(
                    'Request',
                    self.request,
                    '下载没有超时'))
            self._timeout_cl.cancel()
            return result
        #  当规定的时间内_RequestBodyProducer没有收到connectionLost()的时候，强制退出
        if self._transferdata:
            # logger.error("接收body的程序要停止了"
            logger.error(*self.lfm.error("Request",self.request,
                     'DownloadAgent',
                          '在规定的时间内，body没有接收完毕,',),
             extra=
             {
                 'exception':'',
                'time':"\n时间是{:6.3f}".format(time.clock())
             })
            self._transferdata._transport.stopProducing()

        raise TimeoutError("下载 %s 花费的时间超过 %s 秒." % (url, timeout))

    def _cb_body_get(self,transferdata,request):
        # 如果返回的response的Headers中包含了Content-Length，返回一个具体的数值
        # 如果Headers中不包含的话就是UNKNOWN_LENGTH
        if transferdata.length == 0:
            logger.debug("length: ", transferdata.length)

        # 若meta中不存的'download_maxsize'这个值的话，会自动赋上默认值self._maxsize
        maxsize = request.meta.get('download_maxsize',self._maxsize)
        warnsize = request.meta.get('download_warnsize',self._warnsize)
        expected_size = transferdata.length if transferdata.length is not UNKNOWN_LENGTH else -1
        fail_on_dataloss = request.meta.get('download_fail_on_dataloss', self._fail_on_dataloss)

        #  x and y布尔"与" - 如果 x 为 False，x and y 返回 False，否则它返回 y 的计算值。
        if maxsize and expected_size > maxsize :
            error_msg = ("%(url)s 网页的大小(%(size)s)已经超过可容许下载的最大值(%(maxsize)s).")
            error_args = {'url': request.url,"size":expected_size,'maxsize':maxsize}

            logger.error(error_msg,error_args)
            #  twisted.protocols.tls.TLSMemoryBIOProtocol 的方法
            transferdata._transport._producer.loseConnection()
            raise defer.CancelledError(error_msg % error_args)

        def _cancel(_):
            transferdata._transport._producer.abortConnection()

        finished = defer.Deferred(_cancel)
        transferdata.deliverBody(_ResponseReader(
            finished,transferdata,request,maxsize,warnsize,fail_on_dataloss,self.lfm
        ))

        # 表示接收到了数据，用于延迟的判定
        self._transferdata = transferdata
        return finished

    def _cb_body_done(self,result,request,url):
        logger.debug(*self.lfm.crawled("Request",
                                       request,
                          ' Response 已创建'))

        txresponse,body,flags = result #  对应的是finish传递的内容(_transferdata,body," ")
        status = int(txresponse.code)
        header = dict()
        try:
            for k,v in txresponse.headers.getAllRawHeaders():
                header[k] = v
        except KeyError :
            logger.error(*self.lfm.error("request", request,
                                         'header为None'))
        response = Response(url=url,status=status,headers=header,body=body,flags=flags,request=request)
        return response


@implementer(IBodyProducer)
# 向网站发送数据的时候使用的类
class _RequestBodyProducer(object):

    def __init__(self, body):
        self.body = body
        self.length = len(body)

    def startProducing(self, consumer):
        consumer.write(self.body)
        return defer.succeed(None)

    def pauseProducing(self):
        pass

    def stopProducing(self):
        pass


@implementer(IBodyProducer)
class _ResponseReader(Protocol):
    def __init__(self, finished,transferdata,request,maxsize,warnsize,fail_on_dataloss,logformater):
        self.lfm = logformater
        # logger.debug("ResponseReader 已初始化...")
        logger.debug(*self.lfm.crawled("DownloadAgent", '_ResponseReader',
                                       '已初始化'))
        self._finished = finished
        # 用来保存传输的数据，当数据完整后可以使用json转换为python对象
        self._transferdata = transferdata
        self._request = request
        self._maxsize = maxsize
        self._warnsize = warnsize
        self._warnsize_flag = False
        self._fail_on_dataloss = fail_on_dataloss
        self._fail_on_dataloss_warned = False

        self._bytes_received = 0  # 记录body的大小
        self._bodybuf = BytesIO()  # 记录body的内容



    def dataReceived(self, datas):
        """
        直接传输的数据datas为bytes类型的，不加解码转化为str类型是带有转义符号'\':(\'\\u5929\\u732b\\u7cbe\\u9009\')
        datas进行了decode("utf-8")解码后，数据变成了('\u5929\u732b\u7cbe\u9009'),此时解码后的数据类型是str
        因为传输的datas并不是一次性传输完的，所以不能直接使用json转换，而是当数据全部传输完毕后，使用json.loads()
        这时候就不涉及到转码和转义字符的问题了。
        """
        if self._finished.called:
            return

        self._bodybuf.write(datas)
        self._bytes_received += len(datas)

        if self._maxsize and self._bytes_received > self._maxsize:
            logger.error(*self.lfm.error('Request',self._request,'dataReceived',
                        '收取到的信息容量({bytes}) bytes 超过了下载信息的最大值({maxsize}) bytes '.format(
                            bytes= self._bytes_received,
                            maxsize = self._maxsize)
            ))
            # 当下载量超过最大值的时候，把数据缓存变量情况，取消下载
            self._bodybuf.truncate(0)
            """
            执行cancel()后，直接跳到connectionLost,并返回defer，
            注意的是，此defer之后的callbacks都不会被执行
            """
            self._finished.cancel()
        if not self._warnsize_flag:
            if self._warnsize and self._bytes_received > self._warnsize:
                self._reached_warnsize = True
                # logger.warning("从(%(request)s)收取到的信息容量(%(bytes)s) bytes 超过了下载信息的"
                #              "警戒值(%(warnsize)s) bytes " % {
                #     'request' : self._request,
                #     'bytes' : self._bytes_received,
                #     'warnsize' : self._warnsize
                # })
                logger.warning(*self.lfm.crawled('Request', self._request,
                                             '收取到的信息容量({bytes}) bytes 超过了下载信息的警戒值({warnsize}) bytes '.format(
                                                 bytes=self._bytes_received,
                                                 warnsize=self._warnsize),
                                            'dataReceived'
                                             ))
            self._warnsize_flag = True

    def connectionLost(self, reason):
        if self._finished.called:
            return

        body = self._bodybuf.getvalue()

        #  针对不同的loss connection进行问题的处理
        if reason.check(ResponseDone): #  正常完成数据下载
            # callback(data)调用后，能够向defer数据链中传入一个list数据：
            # [True，传入的参数data]，可以实现将获取的body传输到下一个函数中去
            if body == b'':
                # logger.error("<%s> 没有下载到数据..."%self._request.url)
                logger.error(*self.lfm.error('Request', self._request, '',
                                             '没有下载到数据'
                                             ))
            else:
                # logger.warning('<%s> 成功下载' % self._request.url)
                logger.info(*self.lfm.crawled('Request', self._request,
                                                 '数据下载完整'
                                             ))
            self._finished.callback((self._transferdata,body,None))
            return

        #  当body中没有设置Content-Length或者是Transfer-Encoding的时候，
        # response传输完后，会引起这个错误
        if reason.check(PotentialDataLoss):
            # logger.warning("<%s> 内容下载不完整...",self._request.url)
            logger.warning(*self.lfm.crawled('Request', self._request,
                                             '数据下载不完整'
                                             ))
            self._finished.callback((self._transferdata,body,['partial']))
            return

        #  any(x)判断x对象是否为空对象，如果都为空、0、false，则返回false，如果不都为空、0、false，则返回true
        if reason.check(ResponseFailed) and any(r.check(_DataLoss) for r in reason.value.reasons):
            # logger.error("<%s> 内容下载失败，详情在debug模式下查看..."%self._request.url)
            # logger.debug("<%s> 内容下载失败:%s..."%(self._request.url,reason.getErrorMessage()))
            logger.error(*self.lfm.error('Request', self._request, '',
                                         '内容下载失败:'
                                         ),
                        extra =
                        {
                            'exception': reason.getErrorMessage(),
                        }
            )
            if not self._fail_on_dataloss:
                #  当数据超过下载值得时候，_fail_on_dataloss是用来控制，要不要接收已收的部分数据
                #  默认是将数据抛掉·
                # logger.debug("<%s> 内容下载不完整..."%self._request)
                logger.debug(*self.lfm.crawled('Request', self._request,
                                                 '数据下载不完整'))
                self._finished.callback((self._transferdata,body,['dataloss']))
                return

            elif not self._fail_on_dataloss_warned :
                # logger.debug("<%s> 内容有丢失，如果要处理这个错误的话，在默认设置中"
                #                "将DOWNLOAD_FAIL_ON_DATALOSS = False"
                #                %self._transferdata.request.absoluteURI.decode())
                logger.debug(*self.lfm.crawled('Request', self._transferdata.request.absoluteURI.decode(),
                            '内容有丢失，如果要处理这个错误的话，在默认设置中将DOWNLOAD_FAIL_ON_DATALOSS = False'))
                self._fail_on_dataloss_warned = True

        self._finished.errback(reason)



