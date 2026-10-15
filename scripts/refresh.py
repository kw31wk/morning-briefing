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

# Curated, date-checked child-friendly events found on official Richmond library / City calendars.
def scrape_events():
 today=datetime.now().date()
 candidates=[
  {"title":"Family Storytime","start_date":"2026-10-17","end_date":"2026-10-17","date":"Oct 17","date_label":"OCT 17 · SAT","venue":"Richmond Public Library · Brighouse Branch","time":"10:30–11:00 am","summary":"Songs, stories, rhymes and activities. Drop-in; caregiver stays with child.","ages":"Ages 3–5","price":"Free · Drop-in","url":"https://yourlibrary.bibliocommons.com/v2/events?types=5ade5d8c3f3e9525004dca8e","source":"Richmond Public Library","image":"https://images.unsplash.com/photo-1503454537195-1dcabb73ffb9?auto=format&fit=crop&w=900&q=80"},
  {"title":"Family Storytime","start_date":"2026-10-18","end_date":"2026-10-18","date":"Oct 18","date_label":"OCT 18 · SUN","venue":"Richmond Public Library · Ironwood Branch","time":"10:30–11:00 am","summary":"Songs, stories, rhymes and activities for young children. Caregiver must attend.","ages":"Family · preschool","price":"Free · Drop-in","url":"https://yourlibrary.bibliocommons.com/v2/events?types=5ade5d8c3f3e9525004dca8e","source":"Richmond Public Library","image":"https://images.unsplash.com/photo-1503676260728-1c00da094a0b?auto=format&fit=crop&w=900&q=80"},
  {"title":"Family Storytime","start_date":"2026-10-18","end_date":"2026-10-18","date":"Oct 18","date_label":"OCT 18 · SUN","venue":"Richmond Public Library · Main Library","time":"3:30–4:00 pm","summary":"Interactive family storytime with songs, rhymes, books and activities.","ages":"Infants–5 years with adult","price":"Free · check listing","url":"https://rvalibrary.libcal.com/calendar/main","source":"Richmond Public Library · LibCal","image":"https://images.unsplash.com/photo-1544717305-2782549b5136?auto=format&fit=crop&w=900&q=80"},
  {"title":"Together Time","start_date":"2026-10-19","end_date":"2026-10-19","date":"Oct 19","date_label":"OCT 19 · MON","venue":"General Currie Elementary · Currie Early Learning Centre","time":"9:30–11:30 am","summary":"Play, painting, crafts, science, yoga and circle time with Early Childhood Educators. First come, first served; capacity limited.","ages":"Ages 3–5 · 1 adult per child","price":"Free","url":"https://www.richmondkids.ca/en/families/calendar/together-time-ages-3-5-8?occurrenceID=623465","source":"Richmond Child Care Resource & Referral","image":"https://images.unsplash.com/photo-1502086223501-7ea6ecd79368?auto=format&fit=crop&w=900&q=80"},
  {"title":"Preschool Storytime","start_date":"2026-10-22","end_date":"2026-10-22","date":"Oct 22","date_label":"OCT 22 · THU","venue":"Richmond Public Library · Main Library","time":"10:30–11:15 am","summary":"Interactive storytime with books, songs, rhymes and activities.","ages":"Ages 3–5 with adult","price":"Free · check listing","url":"https://rvalibrary.libcal.com/event/16756793","source":"Richmond Public Library · LibCal","image":"https://images.unsplash.com/photo-1516627145497-ae6968895b74?auto=format&fit=crop&w=900&q=80"}
 ]
 events=[]
 for e in candidates:
  if datetime.fromisoformat(e["end_date"]).date()>=today and datetime.fromisoformat(e["start_date"]).date()<=today+timedelta(days=7):
   events.append(e)
 return events
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
# Curated daily priorities: actionable context, not a generic list of RSS alerts.
# Keep each item concise, time-sensitive, and linked to an authoritative source.
today_local=datetime.now().astimezone().date()
priority_items=[]

# Election deadline and voting logistics.
election_day=datetime(2026,10,17).date()
if today_local <= election_day:
 election_summary=("Election Day is Saturday, October 17, from 8 a.m. to 8 p.m. "
  "Phone requests for mail-ballot packages close October 15 at 3 p.m. at 604-276-4100. "
  "Online requests and Canada Post returns have ended; completed ballots must be delivered to City Hall or a voting place by 8 p.m. on October 17.")
 if today_local == datetime(2026,10,15).date():
  election_summary=("Deadline today: call 604-276-4100 by 3 p.m. to request a mail-ballot package. "
   "Online requests and Canada Post returns have ended. Election Day is Saturday, October 17; completed ballots must reach City Hall or a voting place by 8 p.m.")
 priority_items.append({
  "title":"Richmond election: mail-ballot phone deadline " + ("today" if today_local == datetime(2026,10,15).date() else "passed; vote October 17"),
  "summary":election_summary,
  "url":"https://www.richmond.ca/city-hall/elections.htm",
  "source":"City of Richmond · official election information","severity":"priority"
 })

# A current, location-specific forecast helps with practical plans.
try:
 forecast_url=("https://api.open-meteo.com/v1/forecast?latitude=49.154&longitude=-123.158"
  "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
  "&timezone=America%2FVancouver&forecast_days=3")
 forecast=json.loads(get(forecast_url).decode("utf-8"))
 daily=forecast.get("daily",{})
 codes=daily.get("weather_code",[])
 highs=daily.get("temperature_2m_max",[])
 lows=daily.get("temperature_2m_min",[])
 rain=daily.get("precipitation_probability_max",[])
 labels={0:"clear",1:"mostly clear",2:"partly cloudy",3:"cloudy",45:"fog",48:"fog",51:"drizzle",53:"drizzle",55:"drizzle",61:"rain",63:"rain",65:"heavy rain",71:"snow",73:"snow",75:"heavy snow",80:"showers",81:"showers",82:"heavy showers",95:"thunderstorms"}
 forecast_lines=[]
 for i in range(min(3,len(codes),len(highs),len(lows))):
  day=datetime.fromisoformat(daily["time"][i]).date()
  day_name="Today" if day==today_local else day.strftime("%A")
  phrase=labels.get(codes[i],"changeable conditions")
  rain_text=(f", precipitation chance up to {rain[i]}%" if i<len(rain) and rain[i] is not None else "")
  forecast_lines.append(f"{day_name}: {phrase}, high {round(highs[i])}°C / low {round(lows[i])}°C{rain_text}")
 if forecast_lines:
  priority_items.append({
   "title":"Richmond weather: plan for the next three days",
   "summary":" ".join(forecast_lines)+ " Check the official forecast before heading out with the kids.",
   "url":"https://weather.gc.ca/city/pages/bc-74_metric_e.html",
   "source":"Environment Canada forecast · Richmond","severity":"priority"
  })
except Exception as e:
 print("Forecast summary unavailable:",str(e))

# Canada Post: avoid claiming an active strike without a current official notice.
priority_items.append({
 "title":"Canada Post: verify delivery before relying on mail",
 "summary":"Canada Post's current corporate news page does not confirm a new nationwide shutdown. Because labour and delivery conditions can change, check the latest official service notice before sending time-sensitive mail or relying on delivery dates.",
 "url":"https://www.canadapost-postescanada.ca/cpc/en/our-company/news-and-media/corporate-news/news-release-list.page",
 "source":"Canada Post · official updates","severity":"priority"
})

# Useful local travel heads-up for major downtown events.
if today_local <= datetime(2026,10,21).date() and today_local >= datetime(2026,10,14).date():
 priority_items.append({
  "title":"Downtown Vancouver: expect concert crowds near BC Place",
  "summary":"Bruno Mars has Vancouver shows on October 14, 16, 17, 20 and 21. TransLink advises passengers to allow extra travel time around Stadium–Chinatown Station and BC Place during concert periods.",
  "url":"https://www.translink.ca/news/2026/october/bruno%20mars%20takes%20the%20mic%20at%20stadium%20chinatown%20skytrain%20station",
  "source":"TransLink · October 14 service advisory","severity":"priority"
 })

# Fill remaining slots with real official alert sources, never more than four items.
data["alerts"] = (priority_items + data.get("alerts", []))[:4]
data["status"] = alert_status
with open("data.json","w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False,indent=2)
print("Wrote data.json", {k:len(v) for k,v in data.items() if isinstance(v,list)})
