import json, urllib.request, xml.etree.ElementTree as ET, re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

FEEDS = {
 "world": [
  ("Al Jazeera","https://www.aljazeera.com/xml/rss/all.xml"),
  ("CBC World","https://www.cbc.ca/webfeed/rss/rss-world"),
  ("BBC World","https://feeds.bbci.co.uk/news/world/rss.xml")
 ],
 "local": [
  ("CBC British Columbia","https://www.cbc.ca/webfeed/rss/rss-britishcolumbia"),
  ("City of Richmond","https://www.richmond.ca/rss/news.xml"),
  ("Global BC","https://globalnews.ca/bc/feed/")
 ],
 "hk": [
  ("BBC 中文（繁體）","https://feeds.bbci.co.uk/zhongwen/trad/rss.xml"),
  ("Hong Kong Free Press","https://hongkongfp.com/feed/")
 ]
}
def get(url):
 req=urllib.request.Request(url,headers={"User-Agent":"MorningBriefing/1.0 (personal RSS reader)"})
 with urllib.request.urlopen(req,timeout=18) as r: return r.read()
def parse(feedname,url,limit=6):
 out=[]
 try:
  root=ET.fromstring(get(url))
  items=root.findall(".//item")
  if not items:
   items=root.findall(".//{http://www.w3.org/2005/Atom}entry")
  for it in items:
   def val(*paths):
    for p in paths:
     el=it.find(p)
     if el is not None and (el.text or el.attrib.get("href")): return (el.text or el.attrib.get("href") or "").strip()
    return ""
   title=val("title","{http://www.w3.org/2005/Atom}title")
   link=val("link","{http://www.w3.org/2005/Atom}link")
   if not link:
    el=it.find("{http://www.w3.org/2005/Atom}link")
    if el is not None: link=el.attrib.get("href","")
   desc=val("description","summary","{http://www.w3.org/2005/Atom}summary")
   desc=re.sub("<[^>]+>"," ",desc)
   desc=re.sub(r"\s+"," ",desc).strip()
   pub=val("pubDate","published","updated","{http://www.w3.org/2005/Atom}published")
   try: published=parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat() if pub else datetime.now(timezone.utc).isoformat()
   except: published=datetime.now(timezone.utc).isoformat()
   if title and link.startswith("http"):
    out.append({"title":title,"summary":desc[:260],"url":link,"published":published,"source":feedname})
   if len(out)>=limit: break
 except Exception as e:
  print("Feed unavailable:",feedname,url,str(e))
 return out
data={"updated":datetime.now(timezone.utc).isoformat(),"status":"RSS sources checked; verify stories at publisher","world":[],"local":[],"hk":[],"alerts":[]}
for section,feeds in FEEDS.items():
 for name,url in feeds:
  data[section].extend(parse(name,url,5))
 # deduplicate by normalized headline
 seen=set(); uniq=[]
 for item in data[section]:
  key=re.sub(r"[^a-z0-9]","",item["title"].lower())
  if key not in seen: seen.add(key); uniq.append(item)
 data[section]=uniq[:8]
# Alerts deliberately avoid making unsupported claims; users can open official local sources.
data["alerts"]=[{"title":"Check local advisories before travel","summary":"No automated emergency alert feed is configured. Check official notices for time-sensitive disruptions.","url":"https://www.richmond.ca/","source":"City of Richmond"}]
with open("data.json","w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False,indent=2)
print("Wrote data.json", {k:len(v) for k,v in data.items() if isinstance(v,list)})
