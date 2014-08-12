#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

# Harvest list of files from a KB-webpage
# Match these to id's
# get metadata for each id
# output as xml

#----------------------------------------------------------------------------------------
import ujson, codecs
from lxml import html, etree
import requests
from common import Common #reuse Swedish date-logic from LSH upload

class KBHarvester(object):
    
    def __init__(self):
        self.url = 'https://data.kb.se/datasets/2014/06/kartor/'
        self.credit = u'Kungliga_Biblioteket'
        self.items = {}
        f = open('marccountry.json','r')
        self.marccountry = ujson.load(f)
        f.close()
        f = open('marcrelator.json','r')
        self.marcrelator = ujson.load(f)
        f.close()
        f = open('iso6392b.json','r')
        self.iso6392B = ujson.load(f)
        f.close()
        f = open('occupation.json','r')
        self.occupation = ujson.load(f)
        f.close()
    
    def scraper(self):
        page = requests.get(self.url)
        tree = html.fromstring(page.text)
        
        #@TODO
        #load list of processed id's and last changedate (no need to do those twice)
        
        #get changedate
        changeDate = tree.xpath('//span[@property="dateModified"]/text()')[0]
        fileNames = tree.xpath('//table[@id="files"]//a/text()')
        fileUrls = tree.xpath('//table[@id="files"]//a/@href')
        
        if not len(fileNames) == len(fileUrls):
            print "Oups"
            exit(1)
        
        for i in range(0, len(fileNames)):
            fileId = fileNames[i].split('_')[0]
            self.items[fileId] = {'filename':fileNames[i], 'url':fileUrls[i], 'librisId':fileId }#, 'fileName':outputName }
        
        #Output any troubles
        for k,v in self.items.iteritems():
            troubles = self.getMetadata(k)
            if troubles:
                print k
                for t in troubles:
                    print u'  %s' %t
        
        #@TODO
        #output list of id's + changeDate to log
        self.prepareForWiki() #puts formated values in self.wikiItems
        #output to xml for GWtoolset
        #output to csv, for overview
        tmpPrint(self.items, 'scrape.csv')
        tmpPrint(self.wikiItems, 'wiki.csv')
    
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
        handledTags = [] #tags which are handled below (appended as they get processed)
        skippedTags = ['recordInfo', 'classification', 'genre', 'relatedItem', 'typeOfResource', 'identifier', 'location'] #tags which are knowingly skipped
        
        #Identify title(s)
        handledTags.append('titleInfo')
        crap = '[Kartografiskt material]' #strip this
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
        handledTags.append('name')
        people=[]
        for tag in tree.xpath('//-:name', namespaces=ns):
            if tag.getparent().tag != root: continue #don't want relatedInformation
            if 'type' in tag.attrib and tag.attrib['type'] == 'personal':
                person = {'name':None, 'role':[], 'date':None} #a person can have multiple roles
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
                        role = [] #a person can have multiple roles
                        for cchild in child.getchildren():
                            if cchild.tag[len(poo):] == 'roleTerm' and cchild.attrib['type'] == 'text' and cchild.attrib['authority'] == 'marcrelator':
                                person['role'].append(cchild.text)
                            elif cchild.tag[len(poo):] == 'roleTerm' and cchild.attrib['type'] == 'code' and cchild.attrib['authority'] == 'marcrelator':
                                person['role'].append(cchild.text)
                    else:
                        troubles.append("uncaught person %s" %child.tag[len(poo):])
                if len(person['role']) == 0:
                    person['role'] = None
                #only include role=creator (for now)
                #if 'creator' in person['role']:
                #    people.append(person)
                people.append(person)
            else:
                troubles.append("uncaught name/%s" %child.tag[len(poo):])
        item['people'] = people
        
        #origin info
        handledTags.append('originInfo')
        origin = {'publisher':None, 'placeCountry':None, 'placeSub':None, 'dateIssued':None, 'issuance':None, 'edition':None}
        for tag in tree.xpath('//-:originInfo', namespaces=ns):
            if tag.getparent().tag != root: continue #don't want relatedInformation
            #go through each possibility else output to see if there is anything useful
            for child in tag.getchildren():
                if child.tag[len(poo):] == 'dateIssued':
                    if origin['dateIssued'] is None: #don't overwrite
                        origin['dateIssued'] = child.text.strip(' []')
                elif child.tag[len(poo):] == 'issuance':
                    origin['issuance'] = child.text
                elif child.tag[len(poo):] == 'publisher':
                    origin['publisher'] = child.text.strip(' []')
                elif child.tag[len(poo):] == 'edition':
                    origin['edition'] = child.text
                elif child.tag[len(poo):] == 'place':
                    for cchild in child.getchildren():
                        if cchild.tag[len(poo):] == 'placeTerm':
                            if cchild.attrib['type'] == 'code' and cchild.attrib['authority'] == 'marccountry':
                                origin['placeCountry'] = cchild.text
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
        handledTags.append('language')
        languages=[]
        for tag in tree.xpath('//-:language', namespaces=ns):
            language = {'code':None, 'iso':None}
            for child in tag.getchildren():
                if child.tag[len(poo):] == 'languageTerm' and child.attrib['type'] == 'code':
                    language['iso'] = child.attrib['authority']
                    language['code'] = child.text
                    languages.append(language)
                else:
                    troubles.append("language/@%s %s is unhandled" %(child.attrib, child.tag[len(poo):]))
        item['languages'] = languages
        
        #Geospatial
        handledTags.append('subject')
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
            troubles.append("there were coordinates but none were registered")
        item['geospatial'] = geospatial
        
        #physical
        handledTags.append('physicalDescription')
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
        handledTags.extend(['note', 'tableOfContents', 'abstract'])
        descriptions = {'notes':[], 'toc':None, 'abstract':None}
        for tag in tree.xpath('//-:note', namespaces=ns):
            descriptions['notes'].append(tag.text)
        for tag in tree.xpath('//-:tableOfContents', namespaces=ns):
            if descriptions['toc']: troubles.append("fount two ToC")
            descriptions['toc'] = tag.text
        for tag in tree.xpath('//-:abstract', namespaces=ns):
            if descriptions['abstract']: troubles.append("fount two abstracts")
            descriptions['abstract'] = tag.text
        item['descriptions'] = descriptions
        
        #loop over all tags in <mods> to see if any tags are unhandled
        tag = tree.xpath('//-:mods', namespaces=ns)[0]
        for child in tag.getchildren():
            if not child.tag[len(poo):] in (handledTags+skippedTags):
                troubles.append("%s is an unhandled tag: %s" %(child.tag[len(poo):], child.text))
        
        #temp
        self.items[librisId].update(item)
        return troubles
    
    def prepareForWiki(self):
        """
        Prepares the item metadata for on-wiki formating
        """
        self.wikiItems = {}
        for k, v in self.items.iteritems():
            formated = {'description':'',
                        'title':'',
                        'author':'',
                        'map_date':'',
                        'location':'',
                        'projection':'',
                        'scale':'',
                        'latitude':'',
                        'longitude':'',
                        'language':'',
                        'publisher':'',
                        'print_date':'',
                        'sheet':'',
                        'medium':'',
                        'dimensions':'',
                        'notes':''}
            
            #description
            fDesc = []
            if v['descriptions']['abstract']:
                fDesc.append(v['descriptions']['abstract'])
            if v['descriptions']['toc']:
                fDesc.append(v['descriptions']['toc'])
            if len(fDesc) >0:
                formated['description'] = u'{{sv|%s}}' %u'\n\n'.join(fDesc)
            
            #title
            if len(v['titles']) != 0:
                fTitles = []
                for t in v['titles']:
                    txt = t['name']
                    if t['subTitle']:
                        txt += u' – %s' %t['subTitle']
                    if t['type']:
                        txt += u' (%s)' %t['type']
                    fTitles.append(txt)
                if len(fTitles)>1:
                    fTitles[0] = u'* %s' %fTitles[0]
                formated['title'] = u'\n* '.join(fTitles)
            
            #creator(s)
            if len(v['people']) != 0:
                fPeople = []
                for p in v['people']:
                    fPeople.append(self.formatPerson(p))
                if len(fPeople)>1:
                    fPeople[0] = u'* %s' %fPeople[0]
                formated['author'] = u'\n* '.join(fPeople)
            
            #geospatial
            if v['geospatial']['name']:
                formated['location'] = v['geospatial']['name']
            if v['geospatial']['geographic']:
                if len(formated['location']) >0:
                    formated['location'] = u'{{sv|%s (%s)}}' %(formated['location'], ', '.join(v['geospatial']['geographic']))
                else:
                    formated['location'] = u'{{sv|%s}}' %', '.join(v['geospatial']['geographic'])
            if v['geospatial']['projection']:
                fProj = self.formatProjection(v, v['geospatial']['projection'])
                if fProj:
                    formated['projection'] = fProj
            if v['geospatial']['scale']:
                fScale = self.formatScale(v, v['geospatial']['scale'])
                if fScale:
                    formated['scale'] = fScale
            if v['geospatial']['bbox_dec']:
                formated['latitude']  = '%.5f/%.5f' %(v['geospatial']['bbox_dec'][0],v['geospatial']['bbox_dec'][1])
                formated['longitude'] = '%.5f/%.5f' %(v['geospatial']['bbox_dec'][2],v['geospatial']['bbox_dec'][3])
            if v['geospatial']['temporal']:
                stdDate = Common.stdDate(v['geospatial']['temporal']) #attempt formating
                if stdDate:
                    formated['map_date'] = stdDate
                else:
                    print 'failed to format %s' %v['geospatial']['temporal'] #temp
                    formated['map_date'] = v['geospatial']['temporal']
            
            #language
            if len(v['languages']) != 0:
                fLanguage = []
                multiple = len(v['languages']) >1
                for l in v['languages']:
                    if l['iso'] == 'iso639-2b':
                        fLanguage.append(self.getWikiLanguage(l['code'],multiple))
                    else:
                        fLanguage.append(u'%s (%s)' %(l['code'], l['iso']))
                if len(fLanguage)>1:
                    fLanguage[0] = u'* %s' %fLanguage[0]
                formated['language'] = u'\n* '.join(fLanguage)
            
            #publisher
            fPublisher = ['?',]
            if v['origin']['publisher']:
                if v['origin']['publisher'].lower() != 's.n.': #S.N. being the code for unknown publisher
                    fPublisher[0] = v['origin']['publisher']
            if v['origin']['placeSub']:
                sub = v['origin']['placeSub']
                if sub.count(']')>sub.count('['): #Stray brackets polutes this field
                    #@Note: this will replace all ']' even matching ones
                    sub = sub.replace(']','')
                if sub.lower() != 's.l.': #S.L. being the code for unknown place
                    fPublisher.append(sub)
            if v['origin']['placeCountry']:
                if v['origin']['placeCountry'] != "xx": #xx being the marccountry for unknown
                    fPublisher.append(self.marccountry[v['origin']['placeCountry']])
            if len(fPublisher) > 1:
                if fPublisher[0] == '?':
                    fPublisher[0] = '{{unknown}}'
                formated['publisher'] = ', '.join(fPublisher)
            elif len(fPublisher) == 1 and fPublisher[0] != '?':
                formated['publisher'] = ', '.join(fPublisher)
            
            #print_date
            if v['origin']['dateIssued']:
                stdDate = Common.stdDate(v['origin']['dateIssued']) #attempt formating
                if stdDate:
                    formated['print_date'] = stdDate
                else:
                    print 'failed to format %s' %v['origin']['dateIssued'] #temp
                    formated['print_date'] = v['origin']['dateIssued']
            
            #physical extent
            if v['physical']['extent']:
                ext = v['physical']['extent']
                if ext.count(':') == 1 and ext.count(';') == 1:
                    #common pattern: 1 karta : kopparstick ; plåt 37 x 48 cm
                    p = ext.split(':')
                    formated['sheet'] = p[0].strip()
                    p = p[1].split(';')
                    formated['medium'] = p[0].strip()
                    formated['dimensions'] = p[1].strip()
                else:
                    formated['medium'] = ext
            
            #origin/edition
            #Needed?
            
            #notes:
            if len(v['descriptions']['notes'])>1:
                formated['notes'] = u'\n* '.join(v['descriptions']['notes'])
            
            #store
            formated['filename'] = v['filename']
            formated['url'] = v['url']
            formated['librisId'] = v['librisId']
            self.wikiItems[k] = formated
    
    def formatScale(self, v, scale):
        """
        Formates the scale (if existent) as appropriate for Wiki
        Returns a single string
        Must be called before notes are outputed
        """
        #first move any 'skalstock'
        scales = scale.split(';') #this field has concatenated values
        duds=[]
        for i in range(0,len(scales)):
            scales[i] = scales[i].strip(' \n')
            if len(scales[i]) == 0:
                duds.append(i)
            elif scales[i].startswith('Skalstock'):
                v['descriptions']['notes'].append(scales[i])
                duds.append(i)
        while len(duds)>0: #remove in reverse order
            i = duds.pop()
            del scales[i]
        
        if len(scales) == 0:
            return None
        elif len(scales) > 1:
            scales[0] = u'* %s' %scales[0]
            return u'\n* '.join(scales)
        else: #single entry allows for some interesting options
            scalestartBrace = ('Skala [1:', 'Skala [ca 1:')
            scalestartNoBrace = ( 'Skala 1:', 'Skala ca 1:')
            #Skala [ca 1:130 000]
            if scales[0].startswith(scalestartBrace) and scales[0].endswith(']'):
                scale = scales[0][scales[0].find(':')+1:-1].replace(' ','')
                if Common.is_number(scale):
                    if scales[0].startswith('Skala [ca 1:'):
                        v['descriptions']['notes'].append('Scale is approximate')
                    return scale
            if scales[0].startswith(scalestartNoBrace):
                scale = scales[0][scales[0].find(':')+1:].replace(' ','')
                if Common.is_number(scale):
                    if scales[0].startswith('Skala ca 1:'):
                        v['descriptions']['notes'].append('Scale is approximate')
                    return scale
            return scales[0]

    def formatProjection(self, v, proj):
        """
        Formates the projection (if existent) as appropriate for Wiki
        Returns a single string
        Must be called before notes are outputed
        """
        #first move any 'skalstock'
        if proj.startswith('Skalstock'):
            v['descriptions']['notes'].append(proj)
            return None
        else:
            return proj

    def formatPerson(self, person):
        """
        Given a person ({date, role, name}) this formats a string suitable for Wiki
        """
        txt = person['name'].strip()
        if person['date'] and len(person['date'].strip())>0:
            txt += u' (%s' %person['date']
            if person['role']>0:
                txt += u'; %s' %', '.join(self.formatOccupations(person['role']))
            txt += u')'
        elif person['role']>0:
            txt += u' (%s)' %', '.join(self.formatOccupations(person['role']))
        return txt
    
    def formatOccupations(self, roles):
        """
        Formats the occupation roles for wiki
        """
        fRoles = []
        for r in roles:
            if r == 'creator':
                fRoles.append("'''creator'''")
            elif r in self.occupation.keys():
                fRoles.append("{{Occupation|%s}}" %self.occupation[r])
            else:
                fRoles.append("{{en|%s}}" %self.marcrelator[r])
        return fRoles
    
    def getWikiLanguage(self, code, multiple=False):
        """
        Given an ISO 639-2/B this returns the suitable output for Wiki
        """
        if 'CLDR' in self.iso6392B[code]:
            if not multiple:
                return self.iso6392B[code]['CLDR']
            else:
                return u'{{#language:%s}}' %self.iso6392B[code]['CLDR']
        elif 'iso639-1' in self.iso6392B[code]: #this occurs only for bih/bh
            if not multiple:
                return self.iso6392B[code]['iso639-1']
            else:
                return u'{{#language:%s}}' %self.iso6392B[code]['iso639-1']
        else:
            return u"{{en|%s}}" %self.iso6392B[code]['en']
    
#temp
def tmpPrint(items, outfile):
    """
    Quick and dirty output to csv
    """
    f=codecs.open(outfile,'w','utf-8')
    
    #set up order and header
    item = items.iteritems().next()[1]
    #print items['10397840']
    #pretty(item)
    order = []
    for k,v in item.iteritems():
        if isinstance(v, dict):
            for kk,vv in v.iteritems():
                order.append('%s/%s' %(k,kk))
        else:
            order.append('%s' %k)
    f.write(u'#librisid|%s\n' %'|'.join(order))
    
    #run though all
    for k, v in items.iteritems():
        vals = [k]
        for key in order:
            if '/' in key:
                p = key.split('/')
                value = v[p[0]][p[1]]
            else:
                value = v[key]
            if isinstance(value, list):
                tmp = u''
                for i in value:
                    tmp += unicode(i)+';'
                value = tmp[:-1]
            elif value is None:
                value=''
            vals.append(value.replace('\n','<!>').replace('|','!'))
        f.write('%s\n' %'|'.join(vals))
    f.close()

if __name__ == '__main__':
    usage = """@TODO: Add usage instructions"""
    A = KBHarvester()
    A.scraper()
#EoF
