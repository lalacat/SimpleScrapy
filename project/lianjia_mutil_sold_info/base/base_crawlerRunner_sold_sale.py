import pymongo
from twisted.internet import reactor



# mongodb服务的地址和端口号
from core.crawlerRunner import CrawlerRunner
from project.lianjia_mutil_sold_info.spider.father_spider_sale_sold import ParentSoldSale
from settings import Setting

mongo_url = "127.0.0.1:27017"

# 连接到mongodb，如果参数不填，默认为“localhost:27017”
client = pymongo.MongoClient(mongo_url)

#连接到数据库myDatabase
DATABASE = "LianJia"
db = client[DATABASE]

#连接到集合(表):myDatabase.myCollection
COLLECTION = "XiaoQu"
db_coll = db[COLLECTION ]

projectionFields = {'_id':False}  # 用字典指定
queryArgs = [
    {"total_zone_name":"putuo"},
    {"total_zone_name":"minhang"},
    {"total_zone_name":"xuhui"},
    {"total_zone_name":"baoshan"},
    {"total_zone_name":"yangpu"},
    {"total_zone_name":"songjiang"},
    {"total_zone_name":"changning"},
    {"total_zone_name":"pudong"},
    {"total_zone_name":"jiading"},
    {"total_zone_name":"zhabei"},
    {"total_zone_name":"fengxian"},
    {"total_zone_name":"jiangan"},
    {"total_zone_name":"hongkou"},
    {"total_zone_name":"qingpu"},
    {"total_zone_name":"huangpu"},
    ]

searchRes = db_coll.find({"total_zone_name":"pudong"},{'_id':False})
pudong = searchRes.next()
# print(pprint.pformat(pudong))
all_zone =[]
for query in queryArgs:
    search = db_coll.find(query,{'_id':False})
    while True:
        try:
            next_task = search.next()
            #  task_name = next_task["total_zone_name"][0]
            for name, url in next_task.items():
                if name != 'total_zone_name':
                    all_zone.append(url)
        except StopIteration:
            break


zone_name = "yangpu"
town_urls = {
     # 'beicai': 'https://sh.lianjia.com/xiaoqu/beicai/',
     # 'biyun': 'https://sh.lianjia.com/xiaoqu/biyun/',
     # 'caolu': 'https://sh.lianjia.com/xiaoqu/caolu/',
     # 'chuansha': 'https://sh.lianjia.com/xiaoqu/chuansha/',
     # 'datuanzhen': 'https://sh.lianjia.com/xiaoqu/datuanzhen/',
     # 'gaodong': 'https://sh.lianjia.com/xiaoqu/gaodong/',
     # 'gaohang': 'https://sh.lianjia.com/xiaoqu/gaohang/',
     # 'geqing': 'https://sh.lianjia.com/xiaoqu/geqing/',
     # 'hangtou': 'https://sh.lianjia.com/xiaoqu/hangtou/',
     # 'huamu': 'https://sh.lianjia.com/xiaoqu/huamu/',
     # 'huinan': 'https://sh.lianjia.com/xiaoqu/huinan/',
     # 'jinqiao': 'https://sh.lianjia.com/xiaoqu/jinqiao/',
     # 'jinyang': 'https://sh.lianjia.com/xiaoqu/jinyang/',
     # 'kangqiao': 'https://sh.lianjia.com/xiaoqu/kangqiao/',
     # 'laogangzhen': 'https://sh.lianjia.com/xiaoqu/laogangzhen/',
     # 'lianyang': 'https://sh.lianjia.com/xiaoqu/lianyang/',
     # 'lingangxincheng': 'https://sh.lianjia.com/xiaoqu/lingangxincheng/',
     # 'lujiazui': 'https://sh.lianjia.com/xiaoqu/lujiazui/',
     # 'nanmatou': 'https://sh.lianjia.com/xiaoqu/nanmatou/',
     # 'nichengzhen': 'https://sh.lianjia.com/xiaoqu/nichengzhen/',
     'sanlin': 'https://sh.lianjia.com/xiaoqu/sanlin/',
     'shibo': 'https://sh.lianjia.com/xiaoqu/shibo/',
     # 'shuyuanzhen': 'https://sh.lianjia.com/xiaoqu/shuyuanzhen/',
     # 'tangqiao': 'https://sh.lianjia.com/xiaoqu/tangqiao/',
     # 'tangzhen': 'https://sh.lianjia.com/xiaoqu/tangzhen/',
     # 'waigaoqiao': 'https://sh.lianjia.com/xiaoqu/waigaoqiao/',
     # 'wanxiangzhen': 'https://sh.lianjia.com/xiaoqu/wanxiangzhen/',
     # 'weifang': 'https://sh.lianjia.com/xiaoqu/weifang/',
     # 'xinchang': 'https://sh.lianjia.com/xiaoqu/xinchang/',
     # 'xuanqiao': 'https://sh.lianjia.com/xiaoqu/xuanqiao/',
     # 'yangdong': 'https://sh.lianjia.com/xiaoqu/yangdong/',
     # 'yangjing': 'https://sh.lianjia.com/xiaoqu/yangjing/',
     # 'yuanshen': 'https://sh.lianjia.com/xiaoqu/yuanshen/',
     # 'yuqiao1': 'https://sh.lianjia.com/xiaoqu/yuqiao1/',
     # 'zhangjiang': 'https://sh.lianjia.com/xiaoqu/zhangjiang/',
     'zhoupu': 'https://sh.lianjia.com/xiaoqu/zhoupu/',
     # 'zhuqiao': 'https://sh.lianjia.com/xiaoqu/zhuqiao/'
    }
town_urls_dict= {
    'anshan':'https://sh.lianjia.com/xiaoqu/anshan/',# 157 156
    # "dongwaitan":'https://sh.lianjia.com/xiaoqu/dongwaitan/',# 144 141
    # 'huangxinggongyuan':'https://sh.lianjia.com/xiaoqu/huangxinggongyuan/',#159 159
    # 'kongjianglu':'https://sh.lianjia.com/xiaoqu/kongjianglu/',
    # 'wujiaochang':'https://sh.lianjia.com/xiaoqu/wujiaochang/',
    # 'xinjiangwancheng':'https://sh.lianjia.com/xiaoqu/xinjiangwancheng/',
    # 'zhoujiazuilu':'https://sh.lianjia.com/xiaoqu/zhoujiazuilu/',
    # 'zhongyuan1':'https://sh.lianjia.com/xiaoqu/zhongyuan1/',
}

child_urls = {
    'Task_sold_杨思路602号':'https://sh.lianjia.com/chengjiao/c5011000020052/',
    'Task_sold_三新路5弄': 'https://sh.lianjia.com/chengjiao/c5011000018712/'
}

s = Setting()
cr = CrawlerRunner(town_urls_dict,s,ParentSoldSale)
# cr = CrawlerRunner(child_urls, s, CollectSold)
d = cr.start()
d.addBoth(lambda _:reactor.stop())
reactor.run()

