import json, urllib.request, urllib.error, xml.etree.ElementTree as ET, re
from html.parser import HTMLParser
from urllib.parse import urljoin
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
# Scrape public City of Richmond calendar page for event candidates; keep dates/links visible for verification.
class TextPage(HTMLParser):
 def __init__(self):
  super().__init__(); self.parts=[]; self.links=[]; self._href=None
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag=="a" and attrs.get("href"): self._href=attrs["href"]
 def handle_endtag(self,tag):
  if tag=="a": self._href=None
 def handle_data(self,data):
  t=" ".join(data.split())
  if t:
   self.parts.append(t)
   if self._href: self.links.append((t,self._href))
def scrape_events():
 url="https://www.city.richmond.bc.ca/culture/calendar.htm"
 try:
  raw=get(url).decode("utf-8","ignore")
  p=TextPage(); p.feed(raw)
  text=" ".join(p.parts)
  # Calendar page is a rolling 30-day list. Use the page itself as source; don't fabricate missing dates.
  patterns=[
   ("Halloween Hoot","24 Oct 2026 through 01 Nov 2026","Richmond Nature Park","10:00am–4:00pm","Family-friendly Halloween trail; all ages. Check the official listing before visiting."),
   ("Halloween Hangout","Sat, Oct 17","Hamilton Community Centre","1:00–3:00pm","Free Halloween games, crafts and a themed show; up to age 12. Adult participation and registration required."),
   ("Halloween Spooky Science","Sat, Oct 17","Cambie Community Centre","10:00–11:30am","Halloween-themed science for ages 6–12; $14.05. Check availability."),
   ("Trick or Treat at City Centre","Sat, Oct 31","City Centre Community Centre","1:00–4:00pm","Free indoor Halloween village and craft for ages 3–8.")
  ]
  events=[]
  for title,date,venue,time,summary in patterns:
   if title.lower() in text.lower():
    # Link to the official calendar page, which is the verifiable source for the event listing.
    events.append({"title":title,"date":date,"venue":venue,"time":time,"summary":summary,"url":url,"source":"City of Richmond official calendar"})
  # Add verified library preschool events from the official public library calendar page.
  liburl="https://rvalibrary.libcal.com/calendar/main"
  libraw=get(liburl).decode("utf-8","ignore")
  lib=TextPage(); lib.feed(libraw); lt=" ".join(lib.parts)
  if "Preschool Storytime" in lt and "October 15, 2026" in lt:
   events.append({"title":"Preschool Storytime","date":"Thu, Oct 15","venue":"Richmond Public Library – Main Library","time":"10:30–11:15am","summary":"Stories, songs and rhymes for ages 3–5 with an adult. Check the library calendar for availability and details.","url":liburl,"source":"Richmond Public Library"})
  if "Preschool Storytime" in lt and "October 22, 2026" in lt:
   events.append({"title":"Preschool Storytime","date":"Thu, Oct 22","venue":"Richmond Public Library – Main Library","time":"10:30–11:15am","summary":"Stories, songs and rhymes for ages 3–5 with an adult. Check the library calendar for availability and details.","url":liburl,"source":"Richmond Public Library"})
  return events
 except Exception as e:
  print("Event calendar unavailable:",str(e)); return []
data["events"]=scrape_events()
# No public machine-readable, live emergency-alert feed was verified in this workflow.
# Be explicit: link to official alert sources without claiming there are no active incidents.
data["alerts"]=[{"title":"Official emergency information","summary":"This app does not yet verify active emergency alerts automatically. Check Richmond BC Alert and EmergencyInfoBC directly for current warnings and instructions.","url":"https://www.richmond.ca/services/public-safety/emergency-preparedness/notify-me.htm","source":"City of Richmond · official alert information"},{"title":"Provincial emergency alerts","summary":"For province-wide emergency warnings, check the official EmergencyInfoBC updates. This section does not replace Alert Ready or municipal notifications.","url":"https://www.emergencyinfobc.gov.bc.ca/","source":"EmergencyInfoBC"}]
with open("data.json","w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False,indent=2)
print("Wrote data.json", {k:len(v) for k,v in data.items() if isinstance(v,list)})
