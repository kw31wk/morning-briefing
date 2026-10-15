import json, urllib.request, urllib.error, xml.etree.ElementTree as ET, re, html
from html.parser import HTMLParser
from urllib.parse import urljoin
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

FEEDS = {
 "world": [
  ("Reuters World","https://feeds.reuters.com/Reuters/worldNews"),
  ("AP Top News","https://apnews.com/hub/ap-top-news?output=rss"),
  ("BBC World","https://feeds.bbci.co.uk/news/world/rss.xml"),
  ("CBC World","https://www.cbc.ca/webfeed/rss/rss-world"),
  ("Al Jazeera","https://www.aljazeera.com/xml/rss/all.xml")
 ],
 "local": [
  ("CBC British Columbia","https://www.cbc.ca/webfeed/rss/rss-britishcolumbia"),
  ("City of Richmond","https://www.richmond.ca/rss/news.xml"),
  ("Global BC","https://globalnews.ca/bc/feed/"),
  ("Vancouver Is Awesome","https://www.vancouverisawesome.com/rss")
 ],
 "hk": [
  ("RTHK 香港本地新聞","https://rthk.hk/rthk/news/rss/c_expressnews_clocal.xml"),
  ("RTHK 大中華新聞","https://rthk.hk/rthk/news/rss/c_expressnews_greaterchina.xml"),
  ("BBC 中文（繁體）","https://feeds.bbci.co.uk/zhongwen/trad/rss.xml"),
  ("RTHK 財經新聞","https://rthk.hk/rthk/news/rss/c_expressnews_finance.xml")
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
   try:
    if not pub: raise ValueError("missing publication date")
    try: parsed=parsedate_to_datetime(pub)
    except (TypeError,ValueError): parsed=datetime.fromisoformat(pub.replace("Z","+00:00"))
    if parsed.tzinfo is None: parsed=parsed.replace(tzinfo=timezone.utc)
    published=parsed.astimezone(timezone.utc).isoformat()
   except: published=""
   if title and link.startswith("http"):
    out.append({"title":title,"summary":desc[:260],"url":link,"published":published,"source":feedname,"image":image_url})
   if len(out)>=limit: break
 except Exception as e:
  print("Feed unavailable:",feedname,url,str(e))
 return out
data={"updated":datetime.now(timezone.utc).isoformat(),"status":"RSS sources checked; verify stories at publisher","world":[],"local":[],"hk":[],"alerts":[]}
for section,feeds in FEEDS.items():
 per_feed=[]
 for name,url in feeds:
  per_feed.append(parse(name,url,10))
 # Interleave feeds so the first publisher cannot dominate the whole section.
 combined=[]
 for i in range(10):
  for feed_items in per_feed:
   if i<len(feed_items): combined.append(feed_items[i])
 seen=set(); uniq=[]
 cutoff=datetime.now(timezone.utc)-timedelta(hours=30)
 for item in combined:
  key=re.sub(r"[^a-z0-9]","",item["title"].lower())
  if key in seen: continue
  seen.add(key)
  try:
   stamp=datetime.fromisoformat(item.get("published","").replace("Z","+00:00"))
   if stamp.tzinfo is None: stamp=stamp.replace(tzinfo=timezone.utc)
   if stamp < cutoff: continue
  except: continue
  uniq.append(item)
 data[section]=uniq

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
 for item in data[section][:8]:
  if not item.get("image"):
   item["image"]=article_image(item["url"])

# Rank headlines by editorial significance rather than simply taking the first RSS items.
# Scores are transparent heuristics; freshness and publisher diversity are enforced above.
def importance(item, section):
 title=(item.get("title","")+" "+item.get("summary","")).lower()
 score=0
 groups={
  "critical": ["killed","dead","death toll","attack","missile","airstrike","invasion","war","ceasefire","earthquake","flood","hurricane","wildfire","outbreak","pandemic","emergency","crash","explosion","hostage","sanction","strike"],
  "politics": ["president","prime minister","government","election","parliament","congress","court","minister","policy","vote","shutdown","impeach"],
  "economy": ["inflation","interest rate","central bank","recession","economy","jobs","unemployment","trade","tariff","oil price","stock market","budget","bank"],
  "technology": ["cyberattack","data breach","artificial intelligence","ai ","technology","starlink"]
 }
 for group,terms in groups.items():
  if any(term in title for term in terms): score += {"critical":5,"politics":3,"economy":3,"technology":2}[group]
 if section=="local" and any(t in title for t in ["richmond","vancouver","translink","british columbia","b.c.","bc ","school","wildfire","flood","election","canada post","housing","health","cyberattack"]): score+=4
 if section=="hk":
  if item.get("source","").startswith("RTHK"): score+=4
  if any(t in title for t in ["香港","港府","港股","李家超","立法會","恒指","房屋","巴士","學校","警方","本港","大埔","北都","港人","房委會","港鐵","運輸署","醫管局","財政司","行政長官","政府","樓市","樓價","公屋","私樓","按揭","利率","通脹","失業","旅客","旅遊","國安","法院","高等法院","廉署","天氣","暴雨","交通意外","火警","騙案","詐騙","拘捕","加價","減價","最低工資","強積金","輸入外勞"]): score+=6
  if any(t in title for t in ["美國中期選舉","烏克蘭","特朗普","美國總統","中國外交部"]): score-=3
 if section=="world" and any(t in title for t in ["ukraine","iran","russia","israel","gaza","china","north korea","trump","global","united nations"]): score+=2
 if item.get("source","").startswith("Reuters"): score+=2
 if item.get("source","").startswith("AP"): score+=2
 try:
  age=(datetime.now(timezone.utc)-datetime.fromisoformat(item["published"].replace("Z","+00:00"))).total_seconds()/3600
  score += max(0,2-age/15)
 except: pass
 return score

def topic_key(item, section):
 text=(item.get("title","")+" "+item.get("summary","")).lower()
 title_only=item.get("title","").lower()
 if section=="world":
  if any(t in text for t in ["ukraine","zelensky","russian refinery","russia's oil","russia’s oil"]): return "ukraine-russia-war"
  if any(t in text for t in ["yemen","houthi","aden"]): return "yemen-conflict"
  if any(t in text for t in ["trump","midterm","republican","democrat","u.s. election","us election"]): return "us-politics"
  if any(t in text for t in ["iran","oil prices","fuel prices","middle east conflict"]): return "iran-energy"
 if section=="local":
  # Do not let a world story syndicated by a local outlet masquerade as local news.
  local_terms=["richmond","vancouver","burnaby","surrey","british columbia","b.c.","translink","canada line","steveston","metro vancouver","bc ndp","canada post","city council","school district","mayoral","housing","aquatic centre","highway","construction","ferry","skytrain"]
  if not any(t in title_only for t in local_terms): return "not-local"
 if section=="hk":
  local_terms=["香港","港府","港股","李家超","立法會","恒指","房屋","巴士","學校","警方","本港","大埔","北都","港人","港鐵","房委會","港元","旅客","香港人","hong kong","hongkong"]
  if not any(t in title_only for t in local_terms): return "not-hong-kong"
 return ""
# Hong Kong section is strictly Traditional Chinese and Hong Kong-focused.
def has_chinese(text):
 return bool(re.search(r"[\\u4e00-\\u9fff]", text or ""))

for section in ("world","local","hk"):
 if section=="hk":
  data[section]=[
   item for item in data[section]
   if has_chinese(item.get("title",""))
   and topic_key(item,section) != "not-hong-kong"
  ]
  for item in data[section]:
   if not has_chinese(item.get("summary","")):
    item["summary"]="詳情請查看原文報道。"
 data[section].sort(key=lambda item: importance(item,section),reverse=True)
 selected=[]; topics=set()
 for item in data[section]:
  topic=topic_key(item,section)
  if topic=="not-local" or topic=="not-hong-kong": continue
  if topic and topic in topics: continue
  selected.append(item)
  if topic: topics.add(topic)
  if len(selected)==4: break
 data[section]=selected

# Curated family events from current official listings and the farm's live 2026 hours.
# Refresh dates relative to the current date so expired one-off events drop out automatically.
def scrape_events():
 today=datetime.now().astimezone().date()
 def next_weekday(day, include_today=True):
  delta=(day-today.weekday())%7
  if delta==0 and not include_today: delta=7
  return today+timedelta(days=delta)
 def event_date(d):
  return d.strftime("%Y-%m-%d")
 def label(d):
  return d.strftime("%b %d · %a").upper()
 candidates=[]
 # Richmond Country Farms confirms daily pumpkin-patch operation through Oct 31, 2026.
 patch_end=datetime(2026,10,31).date()
 if today<=patch_end:
  d=today
  candidates.append({"title":"Pumpkin Patch at Richmond Country Farms","start_date":event_date(d),"end_date":event_date(patch_end),"date":d.strftime("%b %d"),"date_label":label(d),"venue":"12900 Steveston Highway, Richmond","time":"Weekdays 9 am–4 pm · Weekends 10 am–4:30 pm","summary":"Tractor-wagon ride, pumpkin picking, corn maze, farm animals and seasonal decorations. Open daily through October 31; last entry is 4 pm weekdays and 4:30 pm weekends.","ages":"All ages · family outing","price":"$15 + tax weekdays · $20 + tax weekends; ages 2 and under free","url":"https://richmondcountryfarms.com/pages/hours-location","source":"Richmond Country Farms · official hours","image":"https://images.unsplash.com/photo-1509622905150-fa66d390c9e1?auto=format&fit=crop&w=900&q=80"})
 # Richmond Fire-Rescue confirms this public family-friendly event for Oct 17, 2026.
 fire_date=datetime(2026,10,17).date()
 if today<=fire_date<=today+timedelta(days=7):
  candidates.append({"title":"Kidde Canada & Richmond Fire-Rescue","start_date":event_date(fire_date),"end_date":event_date(fire_date),"date":fire_date.strftime("%b %d"),"date_label":label(fire_date),"venue":"Home Depot Richmond","time":"10 am–2 pm","summary":"Meet Richmond Fire-Rescue's team and learn about home fire safety at this public community event.","ages":"Family-friendly","price":"Free · drop-in","url":"https://firerescue.richmond.ca/event-calendar/list/?posts_per_page=108","source":"Richmond Fire-Rescue · official event calendar","image":"https://images.unsplash.com/photo-1599708153386-62bf8f035c90?auto=format&fit=crop&w=900&q=80"})
 # Official Richmond Public Library listings repeat these programs on Saturdays.
 saturday=next_weekday(5)
 if today<=saturday<=today+timedelta(days=7):
  candidates.append({"title":"Family Storytime (Cambie Library)","start_date":event_date(saturday),"end_date":event_date(saturday),"date":saturday.strftime("%b %d"),"date_label":label(saturday),"venue":"Richmond Public Library · Cambie Branch","time":"10:30–11 am","summary":"Songs, stories, rhymes and more. Drop-in; a parent or caregiver must attend.","ages":"Preschool · family","price":"Free · drop-in","url":"https://yourlibrary.bibliocommons.com/v2/events?series=6a99bdea4cb69d003e258991","source":"Richmond Public Library · official event listing","image":"https://images.unsplash.com/photo-1503454537195-1dcabb73ffb9?auto=format&fit=crop&w=900&q=80"})
  candidates.append({"title":"DUPLO Free Play (Brighouse Library)","start_date":event_date(saturday),"end_date":event_date(saturday),"date":saturday.strftime("%b %d"),"date_label":label(saturday),"venue":"Richmond Public Library · Brighouse Branch","time":"11–11:30 am","summary":"Drop-in building play with DUPLO bricks. No registration needed; caregiver stays with child.","ages":"Ages 2–5","price":"Free · drop-in","url":"https://yourlibrary.bibliocommons.com/v2/events?audiences=5ab2cc261cc59e4b41421b0d","source":"Richmond Public Library · official event listing","image":"https://images.unsplash.com/photo-1587654780291-39c9404d746b?auto=format&fit=crop&w=900&q=80"})
 # Together Time is listed by Richmond Child Care Resource & Referral for preschoolers.
 monday=next_weekday(0)
 if today<=monday<=today+timedelta(days=7):
  candidates.append({"title":"Together Time (Ages 3–5)","start_date":event_date(monday),"end_date":event_date(monday),"date":monday.strftime("%b %d"),"date_label":label(monday),"venue":"General Currie Elementary · Currie Early Learning Centre","time":"9:30–11:30 am","summary":"Play, painting, crafts, science, yoga and circle time with Early Childhood Educators. First come, first served; capacity limited.","ages":"Ages 3–5 · adult participation required","price":"Free","url":"https://www.richmondkids.ca/en/families/calendar/together-time-ages-3-5-8?occurrenceID=623465","source":"Richmond Child Care Resource & Referral","image":"https://images.unsplash.com/photo-1502086223501-7ea6ecd79368?auto=format&fit=crop&w=900&q=80"})
 # Only retain future events in the requested horizon; daily farm visit remains a current option.
 events=[]
 for e in candidates:
  if datetime.fromisoformat(e["end_date"]).date()>=today and datetime.fromisoformat(e["start_date"]).date()<=today+timedelta(days=7):
   events.append(e)
 events.sort(key=lambda e:(e["start_date"],0 if "Pumpkin Patch" in e["title"] else 1))
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
  "source":"City of Richmond · official election information","severity":"priority","image":"https://images.unsplash.com/photo-1540910419892-4a36d2c3266c?auto=format&fit=crop&w=900&q=80"
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
   "source":"Environment Canada forecast · Richmond","severity":"priority","image":"https://images.unsplash.com/photo-1515694346937-94d85e41e6f0?auto=format&fit=crop&w=900&q=80"
  })
except Exception as e:
 print("Forecast summary unavailable:",str(e))

# Canada Post: avoid claiming an active strike without a current official notice.
priority_items.append({
 "title":"Canada Post: verify delivery before relying on mail",
 "summary":"Canada Post's current corporate news page does not confirm a new nationwide shutdown. Because labour and delivery conditions can change, check the latest official service notice before sending time-sensitive mail or relying on delivery dates.",
 "url":"https://www.canadapost-postescanada.ca/cpc/en/our-company/news-and-media/corporate-news/news-release-list.page",
 "source":"Canada Post · official updates","severity":"priority","image":"https://images.unsplash.com/photo-1577705998148-6da4f3963bc8?auto=format&fit=crop&w=900&q=80"
})

# Useful local travel heads-up for major downtown events.
if today_local <= datetime(2026,10,21).date() and today_local >= datetime(2026,10,14).date():
 priority_items.append({
  "title":"Downtown Vancouver: expect concert crowds near BC Place",
  "summary":"Bruno Mars has Vancouver shows on October 14, 16, 17, 20 and 21. TransLink advises passengers to allow extra travel time around Stadium–Chinatown Station and BC Place during concert periods.",
  "url":"https://www.translink.ca/news/2026/october/bruno%20mars%20takes%20the%20mic%20at%20stadium%20chinatown%20skytrain%20station",
  "source":"TransLink · October 14 service advisory","severity":"priority","image":"https://images.unsplash.com/photo-1544620347-c4fd4a3d5957?auto=format&fit=crop&w=900&q=80"
 })

# Fill remaining slots with real official alert sources, never more than four items.
data["alerts"] = (priority_items + data.get("alerts", []))[:4]
data["status"] = alert_status
with open("data.json","w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False,indent=2)
print("Wrote data.json", {k:len(v) for k,v in data.items() if isinstance(v,list)})
