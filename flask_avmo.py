from flask import render_template
from flask import Flask
from flask import request
from flask import redirect
from flask import url_for
import sqlite3
import requests
import json
from lxml import etree
import time
import re
import math
import os
import binascii
app = Flask(__name__)

#数据库列名
'''
0 => id
1 => linkid
2 => title
3 => av_id
4 => release_date
5 => len
6 => director
7 => studio
8 => label
9 => series
10 => genre
11 => stars
12 => director_url
13 => studio_url
14 => label_url
15 => series_url
16 => bigimage
17 => image_len

linkid,title,av_id,release_date,genre,stars,replace(bigimage,"pl.jpg","ps.jpg") as simage,id
'''

#每页展示的数量
PAGE_LIMIT = 30
CDN_SITE = '//jp.netcdn.space'
CDN_SITE = '//pics.dmm.co.jp'
SQL_CACHE = {}
#缓存首页

@app.route('/')
@app.route('/page/<int:pagenum>')
@app.route('/search/<keyword>')
@app.route('/search/<keyword>/page/<int:pagenum>')
def index(keyword = '', pagenum = 1):
    if pagenum < 1:
        redirect(url_for('/'))
    limit_start = (pagenum -1) * PAGE_LIMIT
    keyword = keyword.replace("'",'').replace('"','').strip()

    if re.match('^[a-zA-Z0-9 \-]{4,14}$', keyword):
        tmp = keyword.replace(' ', '-').upper()
        if '-' in tmp:
            return movie(tmp)
        else:
            where = 'av_list.av_id like "%{}%"'.format(tmp)
    elif keyword != '':
        where = ''
        key_list = keyword.split(' ')
        for key_item in key_list:
            if key_item == '字幕':
                where += ' av_163sub.sub_id IS NOT NULL and'
                continue
            if key_item == '已发布':
                date = time.strftime("%Y-%m-%d", time.localtime())
                where += ' av_list.release_date <= "{}" and'.format(date)
                continue
            where += '''
            (av_list.title like "%{0}%" or
            av_list.av_id like "%{0}%" or
            av_list.director like "%{0}%" or
            av_list.studio like "%{0}%" or
            av_list.label like "%{0}%" or
            av_list.series like "%{0}%" or
            av_list.genre like "%{0}%" or
            av_list.stars like "%{0}%")and'''.format(key_item)
        where = where[:-3]
    elif keyword == '':
        where = '1'
    result = sqliteSelect('*', 'av_list', where, (limit_start, PAGE_LIMIT))
    if keyword != '':
        page_root = '/{}/{}'.format('search', keyword)
    else:
        page_root = ''
    return render_template('index.html', data=list_filter(result[0]), cdn=CDN_SITE, pageroot=page_root, page=pagination(pagenum, result[1]), keyword=keyword)

@app.route('/movie/<linkid>')
def movie(linkid=''):
    if linkid=='':
        return redirect(url_for('index'), 404)
    if '-' in linkid:
        where = ' av_list.av_id="{}"'.format(linkid.upper())
    else:
        where = ' av_list.linkid="{}"'.format(linkid)
    sql_arr = sqliteSelect('*', 'av_list', where, (0, 1))

    if sql_arr[0] == []:
        return redirect(url_for('index'),404)
    
    movie = list2dict(sql_arr[0][0])
    #系列
    if movie['genre']:
        movie['genre'] = movie['genre'].split('|')
    #演员
    if movie['stars_url']:
        sql = 'select linkid,name,headimg from av_stars where linkid in ("{}")'.format(
            movie['stars_url'].replace('|','","'))
        stars_data = db_fetchall(sql)
        movie['stars_data'] = []
        for item in stars_data:
            movie['stars_data'].append(
                {
                    'linkid':item[0],
                    'name':item[1],
                    'headimg': 'mono/actjpgs/nowprinting.gif' if item[2] == '' else item[2]
                }
            )
    #图片
    img = []
    if movie['image_len'] != '0':
        count = int(movie['image_len'])
        imgurl = CDN_SITE + '/digital/video' + \
            movie['bigimage'].replace('pl.jpg', '')
        for i in range(1, count+1):
            img.append({
                'small':'{}-{}.jpg'.format(imgurl, i),
                'big':'{}jp-{}.jpg'.format(imgurl, i)
            })
    else:
        img = ''
    movie['imglist'] = img
    return render_template('movie.html', data=movie, cdn=CDN_SITE)

@app.route('/director/<keyword>')
@app.route('/director/<keyword>/page/<int:pagenum>')
@app.route('/studio/<keyword>')
@app.route('/studio/<keyword>/page/<int:pagenum>')
@app.route('/label/<keyword>')
@app.route('/label/<keyword>/page/<int:pagenum>')
@app.route('/series/<keyword>')
@app.route('/series/<keyword>/page/<int:pagenum>')
@app.route('/genre/<keyword>')
@app.route('/genre/<keyword>/page/<int:pagenum>')
@app.route('/stars/<keyword>')
@app.route('/stars/<keyword>/page/<int:pagenum>')
def search(keyword='', pagenum = 1):
    if pagenum < 1:
        return redirect(url_for('index'), 404)
    limit_start = (pagenum - 1) * PAGE_LIMIT

    function = request.path.split('/')[1]
    if function == 'director' or function == 'studio' or function == 'label' or function == 'series' or function == 'stars':
        where = 'av_list.{}_url="{}"'.format(function, keyword)
    if function == 'genre':
        where = 'av_list.{} LIKE "%{}%"'.format(function, keyword)

    page_root = '/{}/{}'.format(function, keyword)
    result = sqliteSelect('*', 'av_list', where, (limit_start, PAGE_LIMIT))

    if function == 'stars':
        keyword = db_fetchall(
            'SELECT name FROM "av_stars" where linkid="{}";'.format(keyword))[0][0]
    
    if function != 'genre' and function != 'stars':
        keyword = ''

    return render_template('index.html', data=list_filter(result[0]), cdn=CDN_SITE, pageroot=page_root, page=pagination(pagenum, result[1]), keyword=keyword)

@app.route('/genre')
def genre():
    result = sqliteSelect('name,title','av_genre',1,(0,500),'',subtitle=False)
    data = {}
    for item in result[0]:
        if item[1] not in data:
            data[item[1]] = []
        data[item[1]].append(item)
    data = list(data.values())
    return render_template('genre.html', data=data, cdn=CDN_SITE)

@app.route('/like/add/<data_type>/<data_val>')
def like_add(data_type=None, data_val=None):
    if data_type != None and data_val != None:
        timetext = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        sqltext = 'REPLACE INTO av_like VALUES("{}", "{}", "{}")'.format(
            data_type, data_val, timetext)
        DB['CUR'].execute(sqltext)
        DB['CONN'].commit()
        return 'ok'
    return ''

@app.route('/like/movie')
@app.route('/like/movie/page/<int:pagenum>')
def like_page(pagenum=1):
    if pagenum < 1:
        return redirect(url_for('index'), 404)
    limit_start = (pagenum - 1) * PAGE_LIMIT

    result = sqliteSelect(column='*', table='av_list', limit=(limit_start, PAGE_LIMIT),
                          othertable=" JOIN av_like ON av_like.type='av_id' AND av_like.val = av_list.av_id ", order='av_like.time DESC')

    return render_template('index.html', data=list_filter(result[0]), cdn=CDN_SITE, pageroot='/like/movie', page=pagination(pagenum, result[1]), keyword='')

@app.route('/like/<keyword>')
def like_page_other(keyword=''):
    map_ = {
        'director':'导演',
        'studio':'制作',
        'label':'发行',
        'series':'系列',
    }
    sqltext = "SELECT av_list.* FROM av_like JOIN (SELECT * FROM av_list GROUP BY {0}_url ORDER BY id DESC )av_list ON av_like.type='{0}' AND av_like.val=av_list.{0}_url".format(
        keyword
    )
    result = db_fetchall(sqltext)
    return render_template('like.html', data=list_filter(result), cdn=CDN_SITE, type_nick=map_[keyword], type_name=keyword, type_url=keyword + '_url')

@app.route('/like/stars')
def like_stars():
    sqltext = 'SELECT s.linkid,s.name,s.headimg FROM "av_like" l join "av_stars" s on l.val=s.linkid where l.type="stars" order by l.time desc'
    result = db_fetchall(sqltext)
    return render_template('stars.html', data=result,cdn=CDN_SITE)

#暂时没用
@app.route('/api/GetMagnet/<keyword>')
def get_magnet(keyword=''):
    s = requests.Session()
    s.headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/68.0.3440.106 Safari/537.36'
    }
    result = []
    if keyword == '':
        return '{}'
    url = 'https://btso.pw/search/{}'.format(keyword)
    main_html = s.get(url).text
    print(url)
    return main_html
    main_tree = etree.HTML(main_html)
    alist = main_tree.xpath('/html/body/div[2]/div[4]/div[2]/a')

    for item in alist:
        url = 'https:'+item.attrib.get('href')
        item_html = s.get(url).text
        print(url)
        item_tree = etree.HTML(item_html)

        magnet = re.findall('[A-Z0-9]+$', item.attrib.get('href'))[0]

        print(magnet, item.attrib.get('href'))
        result.append([
            item.attrib.get('href'),
            magnet,
        ])
    return json.dumps(result)

def list_filter(data):
    result = []
    for row in data:
        tmp = list2dict(row)
        tmp['smallimage'] = tmp['bigimage'].replace('pl.jpg', 'ps.jpg')
        result.append(tmp)
    return result

def list2dict(row):
    return {
        'id' : row[0],
        'linkid' : row[1],
        'title' : row[2],
        'av_id' : row[3],
        'release_date' : row[4],
        'len' : row[5],
        'director' : row[6],
        'studio' : row[7],
        'label' : row[8],
        'series' : row[9],
        'genre' : row[10],
        'stars' : row[11],
        'director_url' : row[12],
        'studio_url' : row[13],
        'label_url' : row[14],
        'series_url' : row[15],
        'stars_url' : row[16],
        'bigimage' : row[17],
        'image_len' : row[18],
        'sub_id' : row[19] if len(row)>19 else '',
    }

def pagination(pagenum, count):
    pagecount = math.ceil(count / PAGE_LIMIT)
    if pagecount <= 15:
        p1 = 1
        p2 = pagecount
    else:
        if pagenum - 7 < 1:
            p1 = 1
        else:
            p1 = pagenum - 7
        if pagenum + 7 > pagecount:
            p2 = pagecount
        else:
            p2 = pagenum + 7

    pagelist = [x for x in range(p1, p2 + 1)]

    if pagenum != pagecount:
        pageright = pagenum + 1
    else:
        pageright = 0
    if pagenum != 1:
        pageleft = pagenum -1
    else:
        pageleft = 0
    
    return {
        'now': pagenum,
        'left': pageleft,
        'right': pageright,
        'list': pagelist
    }

def conn(dbfile= 'avmoo.db'):
    if os.path.exists('avmoo_.db'):
        dbfile = 'avmoo_.db'
    CONN = sqlite3.connect(dbfile, check_same_thread=False)
    CUR = CONN.cursor()
    return {
        'CONN':CONN,
        'CUR':CUR,
    }

def sqliteSelect(column='*', table='av_list', where='1', limit=(0, 30), order='id DESC', subtitle = True, othertable = ''):
    #db = conn()
    if order.strip() == '':
        order = ''
    else:
        order = 'ORDER BY ' + order
    #是否需要查询字幕
    #LEFT JOIN (SELECT av_id,sub_id FROM av_163sub GROUP BY av_id)av_163sub ON av_list.av_id=av_163sub.av_id
    #,av_163sub.sub_id
    if subtitle:
        sqltext = 'SELECT av_list.{0} FROM av_list {3} WHERE {1} {2}'.format(
            column, where, order, othertable)
    else:
        sqltext = 'SELECT {} FROM {} WHERE {} {}'.format(
            column, table, where, order)
    sqllimit = ' LIMIT {},{}'.format(limit[0], limit[1])
    result = db_fetchall(sqltext + sqllimit)
    res_count = db_fetchall('SELECT COUNT(1) AS count FROM ({})'.format(sqltext))
    return (result, res_count[0][0])
    
def db_fetchall(sql):
    #使用crc32作为key缓存sql结果
    cacheKey = (binascii.crc32(sql.encode()) & 0xffffffff)
    if cacheKey not in SQL_CACHE.keys():
        DB['CUR'].execute(sql)
        SQL_CACHE[cacheKey] = DB['CUR'].fetchall()
        print('SQL EXEC[{}]:'.format(cacheKey))
        print(sql, '\n')
    else:
        print('SQL CACHE[{}]:'.format(cacheKey))
        print(sql, '\n')
    return SQL_CACHE[cacheKey]

    #DB['CUR'].execute(sql)
    #return DB['CUR'].fetchall()

if __name__ == '__main__':
    DB = conn()
    app.run()
