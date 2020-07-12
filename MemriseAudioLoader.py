#!/usr/bin/env python3

import os
import re
import sys
import argparse
import sqlite3
import json
import csv
from gtts import gTTS

from urllib.request import urlopen
from urllib.request import urlretrieve

import requests

from bs4 import BeautifulSoup

# cookeis file exported from EditThisCookie chrome extension in format:
# cookies = [
# {
#    "domain": ".memrise.com",
#    "expirationDate": 1541160876,
#    "hostOnly": false,
#    "httpOnly": false,
#    "name": "ajs_anonymous_id",
#    "path": "/",
#    "sameSite": "no_restriction",
#    "secure": false,
#    "session": false,
#    "storeId": "0",
#    "value": "xxxxxx",
#    "id": 1
#},
#
# Manual changes in the file:
#  - add "cookies = " in begginning of the 1st line
#  - change true -> True
#  - change false -> False

from variables import cookies

MEMRISE_ENDPOINT = "https://www.memrise.com/course/"
MEMRISE_LEVEL_ENDPOINT = "https://www.memrise.com/ajax/level/editing_html/?level_id="
MEMRISE_UPLOAD_ENDPOINT = "https://www.memrise.com/ajax/thing/cell/upload_file/"

class DatabaseManager(object):
    def __init__(self, db):
        self.conn = sqlite3.connect(db)
        self.conn.execute('pragma foreign_keys = on')
        self.conn.commit()
        
        self.cur = self.conn.cursor()
    
    def query(self, *arg):
        self.cur.execute(*arg)
        self.conn.commit()
        return self.cur
    
    def close(self):
        self.conn.close()        

    def __del__(self):
        self.conn.close()
    
class CookiesJar(object):
    def __init__(self):
        print("Initialising cookies jar")
        
        self.cookies = requests.cookies.RequestsCookieJar()

        for cookie in cookies:
            self.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'], path=cookie['path'])
            
    def getCookieValue(self, name):
        for cookie in cookies:
            if(cookie['name'] == name):
                return cookie['value']
        return None

def getAudioFilename(dictionaryDB, word):
    try:
        audioFilename = dictionaryDB.query("SELECT audiofilePath FROM dictionary WHERE word=? AND audiofilePath is not null", [word]).fetchone()[0]
    except:
        print("Audio file for %s not found!" % word)
        return None
    
    return audioFilename
    
def uploadFileToServer(thing_id, cell_id, memriseEditURL, filename, jar):
    
    try:
        files = {'f': (filename, open(filename, 'rb'), 'audio/mp3')}    
    except FileNotFoundError: 
        print(filename + " not found")    
        
    
    form_data = { 
        "thing_id": thing_id, 
        "cell_id": cell_id, 
        "cell_type": "column",
        "csrfmiddlewaretoken": jar.getCookieValue('csrftoken')}
    
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:35.0) Gecko/20100101 Firefox/35.0",
        "referer": memriseEditURL}
    
    r = requests.post(MEMRISE_UPLOAD_ENDPOINT, files=files, cookies=jar.cookies, headers=headers, data=form_data, timeout=60)
    
    if not r.status_code == requests.codes.ok:
        print("Result code: %d" % r.status_code)

def uploadAudio(revision, course, debug, phrasecol, filenamecol, audiocol, gttslang, filedir, source, emptycheck):
    jar = CookiesJar()
    
    print("Opening base URL: %s" % (MEMRISE_ENDPOINT + course))
    memrise = requests.get(MEMRISE_ENDPOINT + course, cookies=jar.cookies)
    
    memriseEditURL = memrise.url + "edit"
    print("Opening edit URL: %s" % memriseEditURL)    
    memriseEdit = requests.get(memriseEditURL, cookies=jar.cookies)
    
    soup = BeautifulSoup(memriseEdit.content, 'html.parser')
    
    try:
        levelId = soup.find(attrs={"data-level-id": True}).attrs['data-level-id']
    except:
        passs    
    
    memriseLevelURL = MEMRISE_LEVEL_ENDPOINT + levelId
    
    print("Opening level URL: %s" % memriseLevelURL)        
    
    memriseLevel = requests.get(memriseLevelURL, cookies=jar.cookies)
    
    thingsJson = json.loads(memriseLevel.content)
    
    thingsHtml = re.sub(r'\n', '', thingsJson['rendered'])

    soup = BeautifulSoup(thingsHtml, 'html.parser')
    things = soup.find_all(attrs={"class": "thing"})
    
    total = 0  
    saved = 0
    
    for thing in things:
        soup = BeautifulSoup(str(thing), 'html.parser')
    
        thingId = soup.find(attrs={"class": "thing", "data-thing-id": True }).attrs['data-thing-id']
        
        # Hardocoded column IDs
        # 1 - English word
        # 3 - Audios
        
        word = soup.find(attrs={"data-cell-type": "column", "data-key": phrasecol }).find(attrs={"class": "text"}).get_text().strip()
        filename = soup.find(attrs={"data-cell-type": "column", "data-key": filenamecol }).find(attrs={"class": "text"}).get_text().strip()
        
        audioFilename = os.path.join(filedir, filename + ".mp3")
                
        AudioFile = soup.find(attrs={"data-cell-type": "column", "data-key": audiocol }).find(string=re.compile("no audio file"))        
        
        if emptycheck == True:
            if(NoAudioFile == None):
                continue
        
        if source == "gttsdir":            
            tts = gTTS(word, tld='com', lang=gttslang)                                            
            
            
            try:
                exists_file = {'f': (audioFilename, open(audioFilename, 'rb'), 'audio/mp3')}
            except FileNotFoundError:                     
                tts.save(audioFilename)
                
                saved += 1
                print(str(saved) + ": gTTS saved " + audioFilename)
            continue
                            
        else:
        
            uploadFileToServer(thingId, audiocol, memriseEditURL, audioFilename, jar)
        
            total += 1
            print(str(total) + ": " + audioFilename )
        
    print("Total number downloaded: %d" % saved)
    print("Total number uploaded: %d" % total)
            
def usage(parser):
    parser.print_help()

def main():
    parser = argparse.ArgumentParser()
    
    parser.add_argument('-revision', type=int, help="Revision to output. Not specfied (default): last, 0 - all", default="-1")
    parser.add_argument('-course', help="Memrise course ID", default="5708953")    
    parser.add_argument('-debug', action='store_true', help="Enable debug ", default=False)    
    parser.add_argument('-phrasecol', help="Headword column", default="3")
    parser.add_argument('-filenamecol', help="Filename column", default="2")
    parser.add_argument('-audiocol', help="Audio column", default="6")    
    parser.add_argument('-gttslang', help="Gtts lang", default="zh-cn")
    parser.add_argument('-filedir', help="Audio dir", default="can")    
    parser.add_argument('-source', help="Source for mp3", default="audiodir")
    parser.add_argument('-emptycheck', help="Check Empty First", default="True")
 
    args = parser.parse_args()

    uploadAudio(
        args.revision,
        args.course,
        args.debug,
        args.phrasecol,
        args.filenamecol,
        args.audiocol,
        args.gttslang,
        args.filedir,
        args.source,
        args.emptycheck
        )

if __name__ == "__main__":
    main()
