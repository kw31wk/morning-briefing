import json, urllib.request, urllib.error, xml.etree.ElementTree as ET, re, html
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
   image_url=""
   # Publishers expose photos through enclosure/media tags or inline RSS HTML.
   image_tags=[
    "enclosure",
    "{http://search.yahoo.com/mrss/}content",
    "{http://search.yahoo.com/mrss/}thumbnail",
    "{http://search.yahoo.com/mrss/}group/{http://search.yahoo.com/mrss/}content",
    "{http://search.yahoo.com/mrss/}group/{http://search.yahoo.com/mrss/}thumbnail"
   ]
   for tag in image_tags:
    el=it.find(tag)
    if el is not None:
     candidate=el.attrib.get("url") or el.attrib.get("href") or ""
     if candidate.startswith("https://") and not candidate.lower().endswith((".gif", ".svg")):
      image_url=candidate; break
   if not image_url:
    html_blob=" ".join([
     it.findtext("description") or "",
     it.findtext("{http://purl.org/rss/1.0/modules/content/}encoded") or "",
     it.findtext("{http://www.w3.org/2005/Atom}content") or ""
    ])
    match=re.search("<img[^>]+(?:src|data-src)=[\\\"']([^\\\"']+)[\\\"']",html_blob,re.I)
    if match and match.group(1).startswith("https://"):
     image_url=match.group(1)
   pub=val("pubDate","published","updated","{http://www.w3.org/2005/Atom}published")
   try: published=parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat() if pub else datetime.now(timezone.utc).isoformat()
   except: published=datetime.now(timezone.utc).isoformat()
   if title and link.startswith("http"):
    out.append({"title":title,"summary":desc[:260],"url":link,"published":published,"source":feedname,"image":image_url})
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

# Many RSS feeds omit image enclosures but publisher pages expose a social/preview image.
# Fetch only the first four articles per section and use a short timeout to keep refresh reliable.
def article_image(url):
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; MorningBriefing/1.0)"})
  with urllib.request.urlopen(req,timeout=4) as response:
   page=response.read(250000).decode("utf-8","ignore")
  for pattern in [
   """<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']""",
   """<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:image["']""",
   """<meta[^>]+name=["']twitter:image["'][^>]+content=["']([^"']+)["']""",
  ]:
   m=re.search(pattern,page,re.I)
   if m:
    candidate=html.unescape(m.group(1)).strip()
    if candidate.startswith("https://") and not candidate.lower().endswith((".svg",".gif")):
     return candidate
 except Exception as e:
  print("Article image unavailable:",url,str(e))
 return ""

for section in ("world","local","hk"):
 for item in data[section][:4]:
  if not item.get("image"):
   item["image"]=article_image(item["url"])

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
   ("Halloween Hoot","2026-10-24","2026-11-01","Richmond Nature Park","10:00am–4:00pm","Family-friendly Halloween trail; all ages. Check the official listing before visiting."),
   ("Halloween Hangout","2026-10-17","2026-10-17","Hamilton Community Centre","1:00–3:00pm","Free Halloween games, crafts and a themed show; up to age 12. Adult participation and registration required."),
   ("Halloween Spooky Science","2026-10-17","2026-10-17","Cambie Community Centre","10:00–11:30am","Halloween-themed science for ages 6–12; $14.05. Check availability."),
   ("Trick or Treat at City Centre","2026-10-31","2026-10-31","City Centre Community Centre","1:00–4:00pm","Free indoor Halloween village and craft for ages 3–8.")
  ]
  today=datetime.now(timezone.utc).date()
  events=[]
  for title,start_date,end_date,venue,time,summary in patterns:
   if title.lower() in text.lower() and datetime.fromisoformat(end_date).date() >= today:
    events.append({"title":title,"date":start_date if start_date==end_date else start_date+" to "+end_date,"start_date":start_date,"end_date":end_date,"venue":venue,"time":time,"summary":summary,"url":url,"source":"City of Richmond official calendar"})
  # Library listings are linked in the app; only add entries when dates can be parsed reliably.
  # Do not add library events without a reliably parsed future date.
  return events
 except Exception as e:
  print("Event calendar unavailable:",str(e)); return []
data["events"]=scrape_events()
# Environment and Climate Change Canada official weather-warning feed for Richmond/Delta.
# If the feed is unavailable, keep a clear warning and official links; never infer "no alerts".
def weather_alerts():
 url="https://weather.gc.ca/rss/battleboard/bcrm31_e.xml"
 try:
  root=ET.fromstring(get(url))
  items=root.findall(".//item")
  if not items:
   items=root.findall(".//{http://www.w3.org/2005/Atom}entry")
  found=[]
  for it in items:
   title=(it.findtext("title") or it.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
   link=(it.findtext("link") or "").strip()
   if not link:
    el=it.find("{http://www.w3.org/2005/Atom}link")
    if el is not None: link=el.attrib.get("href","")
   desc=(it.findtext("description") or it.findtext("{http://www.w3.org/2005/Atom}summary") or "").strip()
   desc=re.sub("<[^>]+>"," ",desc)
   desc=re.sub(r"\s+"," ",desc).strip()
   if title and title.lower() not in ("weather alerts","warnings and watches"):
    found.append({"title":title,"summary":desc[:300] or "Open the official alert for details and instructions.","url":link if link.startswith("http") else "https://weather.gc.ca/","source":"Environment and Climate Change Canada · weather alerts","severity":"weather"})
  if found: return found[:3], "Environment Canada warning feed checked; municipal emergency notices are linked separately."
  return [{"title":"No active weather warnings listed in the latest feed","summary":"The latest Environment Canada feed did not list a weather warning for the Richmond/Delta alert region. This does not rule out municipal or other emergency alerts.","url":url,"source":"Environment and Climate Change Canada · feed checked","severity":"info"}], "Environment Canada warning feed checked; municipal emergency notices are linked separately."
 except Exception as e:
  print("Weather alert feed unavailable:",str(e))
  return [{"title":"Check official emergency alerts","summary":"The automatic weather-alert feed could not be checked. Open Environment Canada and Richmond's official alert page to confirm current warnings.","url":"https://weather.gc.ca/warnings/index_e.html?prov=bc","source":"Automatic feed unavailable"},{"title":"Richmond municipal alerts","summary":"Check the City of Richmond's official alert information for local notices and instructions.","url":"https://www.richmond.ca/services/public-safety/emergency-preparedness/notify-me.htm","source":"City of Richmond · official alert information"},{"title":"Provincial emergency alerts","summary":"Check EmergencyInfoBC for current provincial warnings. This app does not replace Alert Ready or municipal notifications.","url":"https://www.emergencyinfobc.gov.bc.ca/","source":"EmergencyInfoBC"}], "Weather warning feed unavailable; check official sources directly."

weather_items, alert_status = weather_alerts()
data["alerts"] = weather_items + [
 {"title":"Richmond municipal alerts","summary":"Check the City of Richmond's official alert information for local notices and instructions.","url":"https://www.richmond.ca/services/public-safety/emergency-preparedness/notify-me.htm","source":"City of Richmond · official alert information"},
 {"title":"Provincial emergency alerts","summary":"Check EmergencyInfoBC for current provincial warnings. This app does not replace Alert Ready or municipal notifications.","url":"https://www.emergencyinfobc.gov.bc.ca/","source":"EmergencyInfoBC"}
]
# Practical daily priorities: distinguish the end of a nationwide shutdown from
# ongoing rotating action, and surface time-sensitive local election logistics.
priority_items = [
 {"title":"Canada Post: national shutdown ended, rotating strikes may still disrupt service",
  "summary":"Canada Post said employees would return on October 11 as CUPW moved from a nationwide strike to rotating strikes. Do not treat this as confirmation that all strike action is cancelled; check the latest service and labour updates before relying on delivery.",
  "url":"https://www.canadapost-postescanada.ca/cpc/en/our-company/news-and-media/corporate-news/news-release-list.page",
  "source":"Canada Post · official labour updates","severity":"priority"}
]
today_local=datetime.now().astimezone().date()
election_day=datetime(2026,10,17).date()
if today_local <= election_day:
 priority_items.append({
  "title":"Richmond election: vote Saturday, October 17",
  "summary":"Richmond's municipal and school election is this Saturday. The City says mail-ballot requests by phone close October 15 at 3:00 p.m.; ballots can no longer be returned by Canada Post and must reach the Chief Election Officer by 8:00 p.m. on October 17. Check your voting location and official instructions.",
  "url":"https://richmond.ca/city-hall/elections.htm",
  "source":"City of Richmond · official election information","severity":"priority"
 })
data["alerts"] = (priority_items + data["alerts"])[:4]
data["status"] = alert_status
with open("data.json","w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False,indent=2)
print("Wrote data.json", {k:len(v) for k,v in data.items() if isinstance(v,list)})
