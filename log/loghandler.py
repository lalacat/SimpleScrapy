import json
import logging
import time
from collections import defaultdict

import pymongo
from logging.handlers import RotatingFileHandler

# logging.FileHandler


class ConsoleHandler(logging.StreamHandler):

    def __init__(self, filter_error,*args, **kwargs):
        super(ConsoleHandler, self).__init__(*args, **kwargs)
        self.filter_error = filter_error

    # 每进行一次log就会调用这个方法
    def emit(self, record):
        if self.filter_error and record.__dict__['levelno'] >=40:
            return
        if not hasattr(record, 'extra_info'):
            record.__dict__['extra_info'] = ' '
        try:
            msg = self.format(record)
            stream = self.stream
            stream.write(msg)
            stream.write(self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


class ConsoleErrorHandler(logging.StreamHandler):

    def __init__(self, *args, **kwargs):
        super(ConsoleErrorHandler, self).__init__(*args, **kwargs)

    # 每进行一次log就会调用这个方法
    def emit(self, record):
        if hasattr(record,'recordErrUrl'):
            if record.recordErrUrl:
                return None
        if not hasattr(record, 'time'):
            record.__dict__['time'] = ' '
        if not hasattr(record, 'exception'):
            record.__dict__['exception'] = ' '
        try:
            msg = self.format(record)
            stream = self.stream
            stream.write(msg)
            stream.write(self.terminator)
            self.flush()
        except Exception:
            print('ConsoleErrorHandler')
            self.handleError(record)


class RotateFileHandler(RotatingFileHandler):
    #  不覆盖原有的文件，一直生成
    def __init__(self,filename, mode='a', maxBytes=0, backupCount=0, encoding=None, delay=False):
        super(RotateFileHandler, self).__init__(filename=filename,mode=mode,
                                                  maxBytes=maxBytes,
                                                  backupCount=backupCount,
                                                  encoding=encoding,
                                                  delay=delay)

    # 每进行一次log就会调用这个方法
    def emit(self, record):
        """
        Emit a record.

        Output the record to the file, catering for rollover as described
        in doRollover().
        """
        if not hasattr(record, 'extra_info'):
            record.__dict__['extra_info'] = ' '
        try:
            if self.shouldRollover(record):
                self.doRollover()
            logging.FileHandler.emit(self, record)
        except Exception:
            self.handleError(record)


class OnlyOneFileHandler(logging.FileHandler):
    def __init__(self,filename, mode='a', encoding=None, delay=False):
        super(OnlyOneFileHandler, self).__init__(filename=filename,mode=mode,
                                                  encoding=encoding,
                                                  delay=delay)
    def emit(self, record):
        """
        Emit a record.

        If the stream was not opened because 'delay' was specified in the
        constructor, open it before calling the superclass's emit.
        """
        if not hasattr(record, 'extra_info'):
            record.__dict__['extra_info'] = ' '
        if self.stream is None:
            self.stream = self._open()
        logging.StreamHandler.emit(self, record)


class RecordErrorUrl(logging.FileHandler):
    def __init__(self,filename, mode='a', encoding=None, delay=False):
        super(RecordErrorUrl, self).__init__(filename=filename,mode=mode,
                                                  encoding=encoding,
                                                  delay=delay)

    def emit(self, record):
        """
        Emit a record.

        If the stream was not opened because 'delay' was specified in the
        constructor, open it before calling the superclass's emit.
        """
        if not hasattr(record, 'recordErrUrl'):
            return
        if self.stream is None:
            self.stream = self._open()
        try:
            msg = self._format(record)
            stream = self.stream
            json.dump(msg,stream,ensure_ascii=False)
            stream.write(self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)
        # logging.StreamHandler.emit(self, record)

    def _format(self,record):
        format_data = dict()
        if hasattr(record, 'asctime'):
            format_data['asctime'] = record.__dict__['asctime']
        if hasattr(record,'msg'):
            format_data['url'] = record.__dict__['msg']
        if hasattr(record,'filename'):
            format_data['filename'] = record.__dict__['filename']
        if hasattr(record,'reason'):
            format_data['reason'] = record.__dict__['reason']
        if hasattr(record,'exception'):
            format_data['exception'] = record.__dict__['exception']
        if hasattr(record,'time'):
            format_data['time'] = float('%6.3f' %record.__dict__['time'])
        return format_data


class LogToMongDB(logging.Handler):

    def __init__(self,MongDB_URL,MongDB_DATABASE,*args, **kwargs):
        super(LogToMongDB,self).__init__(*args, **kwargs)
        self.MongDB_URl = MongDB_URL
        self.MongDB_DATABASE = MongDB_DATABASE
        # self.MongDB_Collection_Name = MongDB_Collection_Name
        # self.default_format = MONGODB_FORMAT

        self.collection_name = time.strftime('%m/%d/%Y',time.localtime())
        self.bulid_time = time.strftime('%m/%d/%Y %H:%M:%S',time.localtime())

        self.base_date = {'bulid_time':self.bulid_time}
        self.bulid_Flag = True


        self.log_num = 50000
        try:
            self.client = pymongo.MongoClient(self.MongDB_URl)
            self.db = self.client[self.MongDB_DATABASE]

        except Exception as e:
            raise Exception(e)

    def emit(self, record):

        if self.bulid_Flag:
            self.bulid_Flag = False
            self.db_coll = self.db[self.collection_name]
            self.db_coll.insert(self.base_date)
            self._id = self.db_coll.find(self.base_date).next()['_id']
            # print(self._id)
        assert self._id,'没有创建基础信息'

        db_msg = defaultdict(list)
        msg = self.format(record).replace('.','_')

        extra_msg = self._get_extra_info(record)
        # key = str(self.log_num)+':['+record.levelname+']'
        # # db_msg[key] = [msg]
        db_msg[msg] = [{
            'levelname':record.levelname,
            'filename':record.__dict__['filename'],
            'lineno':record.__dict__['lineno']
        }]

        if extra_msg:
            db_msg[msg].append(extra_msg)
        self.log_num +=1

        from bson import ObjectId
        self.db_coll.update(
            {'_id':ObjectId(self._id)},
            {'$set':db_msg})

        length = len(self.db_coll.find({'_id':ObjectId(self._id)}).next())
        if length > self.log_num:
            self.bulid_Flag = True


    def _get_extra_info(self,record):
        extra_msg = {}
        if hasattr(record,'extra_info'):
            extra_msg['extra_info'] =record.__dict__['extra_info']
        if hasattr(record,'exception'):
            extra_msg['exception'] =record.__dict__['exception']
        if hasattr(record,'time'):
            extra_msg['time'] =record.__dict__['time']
        if hasattr(record, 'reason'):
            extra_msg['reason'] = record.__dict__['reason']
        return extra_msg



