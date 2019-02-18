
import pymongo


# mongodb服务的地址和端口号
mongo_url = "127.0.0.1:27017"

# 连接到mongodb，如果参数不填，默认为“localhost:27017”
client = pymongo.MongoClient(mongo_url)

#连接到数据库myDatabase
DATABASE = "PuDong_Sold"
db = client[DATABASE]

#连接到集合(表):myDatabase.myCollection
# COLLECTION = "XiaoQu"
# db_coll = db[COLLECTION ]
#
# projectionFields = {'_id':False}  # 用字典指定
# queryArgs = {"total_zone_name":"pudong"}
#
# searchRes = db_coll.find(queryArgs,projectionFields)

all_collection = db.list_collection_names()
print(len(all_collection))
count = 0
for coll in all_collection:
    # if coll != 'ErrUrl':
    if coll in ['Task_sanlin','Task_zhoupu','Task_shibo']:
        db_coll = db[coll]
        child_num = 0
        all_zone = db_coll.find()
        while True:
            try:
                next_task = all_zone.next()
                n = len(next_task)-2
                # if n != 0 :
                #     print(pprint.pformat(next_task))
                child_num += n
            except StopIteration:
                break
        print('%s ：%d' %(coll,child_num))
        count += child_num

print('一共：%d' %count)