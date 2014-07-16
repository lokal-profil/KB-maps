#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

# Harvest list of files  from a KB-webbpage
# Match these to id's
# get metadata for each id
# output as xml

#Notes
#marccountry = marccountry.json
#marcrelator = http://www.loc.gov/marc/relators/relacode.html
#iso639-2b   = iso6392b.json

#----------------------------------------------------------------------------------------
import ujson
from lxml import html, etree
import requests

class KBHarvester(object):
    
    def __init__(self):
        self.url = 'https://data.kb.se/datasets/2014/06/kartor/'
        self.credit = u'Kungliga_Biblioteket'
        self.items = {}
        f = open('marccountry.json','r')
        self.marccountry = ujson.load(f)
        f.close()
        f = open('iso6392b.json','r')
        self.iso6392B = ujson.load(f)
        f.close()
    
    def scraper(self):
        page = requests.get(self.url)
        tree = html.fromstring(page.text)
        
        #get changedate
        changeDate = tree.xpath('//span[@property="dateModified"]/text()')[0]
        fileNames = tree.xpath('//table[@id="files"]//a/text()')
        fileUrls = tree.xpath('//table[@id="files"]//a/@href')
        
        if not len(fileNames) == len(fileUrls):
            print "Oups"
            exit(1)
        
        for i in range(0, len(fileNames)):
            fileId = fileNames[i].split('_')[0]
            #fileEnding = fileNames[i].split('.')[-1]
            #outputName = u'%s_-_%s_-_%s.%s' %(fileNames[i][len(fileId)+1:-(len(fileEnding)+1)], self.credit, fileId, fileEnding)
            self.items[fileId] = {'filename':fileNames[i], 'url':fileUrls[i], 'librisId':fileId }#, 'fileName':outputName }
        
        #Output any troubles
        for k,v in self.items.iteritems():
            troubles = self.getMetadata(k)
            if troubles:
                print k
                for t in troubles:
                    print u'  %s' %t
        
        #output to xml for GWtoolset
        #output to csv, for overview
    
    def getMetadata(self, librisId):
        """retrieve metadata from libris, parse it and add to items"""
        metadataUrl = 'http://libris.kb.se/xsearch?query=BIBID:(%s)&format=mods&format_level=full' %librisId
        page = requests.get(metadataUrl)
        tree = etree.fromstring(page.content) #content instead of text to avoid unicode
        ns = {'-':'http://www.loc.gov/mods/v3'}
        poo = '{%s}' %ns['-'] #being the namespace which must be scrubbed for comparisons to work
        root = '{%s}mods' %ns['-']
        item = {}
        troubles = [] #anny issues encountered
        
        #Identify title(s)
        crap = '[Kartografiskt material]'
        titles = []
        for tag in tree.xpath('//-:titleInfo', namespaces=ns):
            if tag.getparent().tag == root:  #don't want other titles
                title = {'name':None, 'subTitle':None, 'type':None}
                nonSort = ''
                for child in tag.getchildren():
                    if child.tag[len(poo):] == 'title':
                        title_raw = child.text
                        title['name'] = title_raw.replace(crap,'').strip(' []')
                        if 'type' in child.attrib:
                            title['type'] = child.attrib['type']
                    elif child.tag[len(poo):] == 'subTitle':
                        title['subTitle'] = child.text
                    elif child.tag[len(poo):] == 'nonSort':
                        nonSort = child.text
                    else:
                        troubles.append("unhandled titleInfo/%s" %child.tag[len(poo):])
                title['name'] = u'%s%s' %(nonSort, title['name'])
                titles.append(title)
        item['titles'] = titles
        
        #Identify creator (name, date, role=creator)
        people=[]
        for tag in tree.xpath('//-:name', namespaces=ns):
            if tag.getparent().tag != root: continue #don't want relatedInformation
            if 'type' in tag.attrib and tag.attrib['type'] == 'personal':
                person = {'name':None, 'role':None, 'date':None}
                for child in tag.getchildren():
                    if child.tag[len(poo):] == 'namePart':
                        if 'type' in child.attrib:
                            if child.attrib['type'] == 'date':
                                person['date'] = child.text
                        else:
                            name_raw = child.text
                            if len(name_raw.split(',')) == 2:
                                name_raw = u'%s %s' %(name_raw.split(',')[1], name_raw.split(',')[0])
                            person['name'] = name_raw
                    elif child.tag[len(poo):] == 'role':
                        for cchild in child.getchildren():
                            if cchild.tag[len(poo):] == 'roleTerm' and cchild.attrib['type'] == 'text' and cchild.attrib['authority'] == 'marcrelator':
                                person['role'] = cchild.text
                    else:
                        troubles.append("uncaught person %s" %child.tag[len(poo):])
                people.append(person)
            else:
                troubles.append("uncaught name/%s" %child.tag[len(poo):])
        item['people'] = people
        
        #origin info
        origin = {'publisher':None, 'placeCountry':None, 'placeSub':None, 'dateIssued':None, 'issuance':None, 'edition':None}
        for tag in tree.xpath('//-:originInfo', namespaces=ns):
            #go trhough each possibility else output to se if there is anything useful
            for child in tag.getchildren():
                if child.tag[len(poo):] == 'dateIssued':
                    if origin['dateIssued']: continue #don't overwrite
                    origin['dateIssued'] = child.text.strip(' []')
                elif child.tag[len(poo):] == 'issuance':
                    origin['issuance'] = child.text
                elif child.tag[len(poo):] == 'publisher':
                    origin['publisher'] = child.text
                elif child.tag[len(poo):] == 'edition':
                    origin['edition'] = child.text
                elif child.tag[len(poo):] == 'place':
                    for cchild in child.getchildren():
                        if cchild.tag[len(poo):] == 'placeTerm':
                            if cchild.attrib['type'] == 'code' and cchild.attrib['authority'] == 'marccountry':
                                origin['placeCountry'] = self.marccountry[cchild.text]
                            elif cchild.attrib['type'] == 'text':
                                origin['placeSub'] = cchild.text
                            else:
                                troubles.append("originInfo/place/placeTerm/%s %s is unhandled" %(child.attrib, child.tag[len(poo):]))
                        else:
                            troubles.append("originInfo/place/%s is unhandled" %child.tag[len(poo):])
                else:
                    #output so that it can be dealt with or added to skips
                    troubles.append("originInfo/%s is unhandled" %child.tag[len(poo):])
        item['origin'] = origin
        
        #language
        ## should also be matched to normal code
        languages=[]
        for tag in tree.xpath('//-:language', namespaces=ns):
            language = {'code':None, 'iso':None}
            for child in tag.getchildren():
                if child.tag[len(poo):] == 'languageTerm' and child.attrib['type'] == 'code':
                    if child.attrib['authority'] == 'iso639-2b':
                        language['code'] = self.iso6392B[child.text]
                    else:
                        language['iso'] = child.attrib['authority']
                        language['code'] = child.text
                    languages.append(language)
                else:
                    troubles.append("language/@%s %s is unhandled" %(child.attrib, child.tag[len(poo):]))
        item['languages'] = languages
        
        #Geospatial
        geospatial = {'scale':None, 'bbox_dec':None, 'geographic':[], 'temporal':None, 'projection':None, 'name':None}
        knownSkips = ['topic',]
        missedCoord=False #if coords were encountered but non were added
        for tag in tree.xpath('//-:subject', namespaces=ns):
            #go trhough each possibility else output to se if there is anything useful
            for child in tag.getchildren():
                if child.tag[len(poo):] == 'cartographics':
                    for cchild in child.getchildren():
                        if cchild.tag[len(poo):] == 'scale':
                            if geospatial['scale']: troubles.append("found a second geospatial/scale tag")
                            geospatial['scale'] = cchild.text
                        elif cchild.tag[len(poo):] == 'projection':
                            if geospatial['projection']: troubles.append("found a second geospatial/projection tag")
                            geospatial['projection'] = cchild.text
                        elif cchild.tag[len(poo):] == 'coordinates':
                            #something to select the right one
                            if geospatial['bbox_dec']:
                                continue #skip if exists
                            coord_raw = cchild.text.split(' ')
                            if (len(coord_raw) == 4) and all(len(a) == len('Ddddmmss') for a in coord_raw):
                                bbox = [None,None,None,None] #lat, lat, lon, lon
                                for i in range(0,4):
                                    direction = None
                                    if coord_raw[i][:1] in ['e','n']: direction = 1
                                    elif coord_raw[i][:1] in ['w','v','s']: direction = -1 #for some reason v is also used
                                    else:
                                        troubles.append("%s weird direction in coord: %s" %(librisId, ", ".join(coord_raw)))
                                    #convert to decimal
                                    bbox[i] = direction*(int(coord_raw[i][1:4]) + float(coord_raw[i][4:6])/60.0 + float(coord_raw[i][6:])/3600.0 )
                                geospatial['bbox_dec'] = bbox
                            else:
                                missedCoord = True #remembering that if test is not done if one has already been found
                        elif cchild.tag[len(poo):] not in knownSkips:
                            #output so that it can be dealt with or added to skips
                            troubles.append("subject/cartographics/%s is unhandled" %cchild.tag[len(poo):])
                elif child.tag[len(poo):] == 'geographic':
                    geospatial['geographic'].append(child.text)
                elif child.tag[len(poo):] == 'temporal':
                    if geospatial['temporal']: troubles.append("found a second geospatial/temporal tag")
                    geospatial['temporal'] = child.text
                elif child.tag[len(poo):] == 'name':
                    if geospatial['name']: troubles.append("found a second geospatial/name tag")
                    for cchild in child.getchildren():
                        if cchild.tag[len(poo):] == 'namePart':
                            addon = ''
                            if 'type' in cchild.attrib:
                                addon = ' (%s)' %cchild.attrib['type']
                            geospatial['name'] = u'%s%s' %(cchild.text, addon)
                        else:
                            troubles.append("subject/name/%s is unhandled" %cchild.tag[len(poo):])
                elif child.tag[len(poo):] not in knownSkips:
                    #output so that it can be dealt with or added to skips
                    troubles.append("subject/%s is unhandled" %child.tag[len(poo):])
        if missedCoord:
            troubles.append("there were coordinates but none was registered")
        item['geospatial'] = geospatial
        
        #physical
        physical = {'extent':None}
        knownSkips = ['form',]
        for tag in tree.xpath('//-:physicalDescription', namespaces=ns):
            for child in tag.getchildren():
                if child.tag[len(poo):] == 'extent':
                    physical['extent'] = child.text
                elif child.tag[len(poo):] not in knownSkips:
                    troubles.append("uncaught physicalDescription/%s" %child.tag[len(poo):])
        item['physical'] = physical
        
        #descriptions
        physical = {'notes':[], 'toc':None, 'abstract':None}
        for tag in tree.xpath('//-:note', namespaces=ns):
            physical['notes'].append(tag.text)
        for tag in tree.xpath('//-:tableOfContents', namespaces=ns):
            if physical['toc']: troubles.append("fount two ToC")
            physical['toc'] = tag.text
        for tag in tree.xpath('//-:abstract', namespaces=ns):
            if physical['abstract']: troubles.append("fount two abstracts")
            physical['abstract'] = tag.text
        
        #loop over all tags in <mods> to see if any are unhandled
        handledTags = ['titleInfo', 'name', 'originInfo', 'language', 'subject', 'physicalDescription', 'note', 'tableOfContents', 'abstract']
        skippedTags = ['recordInfo', 'classification', 'genre', 'relatedItem', 'typeOfResource', 'identifier', 'location']
        tag = tree.xpath('//-:mods', namespaces=ns)[0]
        for child in tag.getchildren():
            if not child.tag[len(poo):] in (handledTags+skippedTags):
                troubles.append("%s is an unhandled tag: %s" %(child.tag[len(poo):], child.text))
        
        #temp
        self.items[librisId] = item
        return troubles
#temp
def pretty(d, indent=0):
    basic = u'  '
    for key, value in d.iteritems():
        print basic * indent + unicode(key)
        if isinstance(value, dict):
            pretty(value, indent+1)
        else:
            print basic * (indent+1) + unicode(value)

if __name__ == '__main__':
    usage = """Add usage instructions"""
    A = KBHarvester()
    A.scraper()
    #A.getMetadata(u'10372816')
    #A.getMetadata(u'10391328')
#EoF
