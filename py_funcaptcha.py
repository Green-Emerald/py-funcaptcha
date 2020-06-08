import requests
import random
import time
import httpagentparser
from urllib.parse import urlsplit
from requests.packages.urllib3.exceptions import InsecureRequestWarning
## For image manipulation
from PIL import Image
from io import BytesIO
## Modules for encryption and decryption
from Crypto.Cipher import AES
import base64
import hashlib
import json
import string
import re
import secrets


## Default params
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.61 Safari/537.36"
USE_FAKE_HASHES = True


mm3js = None
if not USE_FAKE_HASHES:
    ## Load .js module for murmur3 related functions (used in BDA/fingerprint2 generation)
    import execjs
    with open("fp.js") as f:
        mm3js = execjs.compile(f.read())


## Create dict of fields from full token string
def parse_full_token(token):
    token = "token=" + token
    assoc = {}

    for field in token.split("|"):
        s = field.partition("=")
        key, value = s[0], s[-1]
        assoc[key] = value
    
    return assoc


## Get random float value
def get_float():
    return random.uniform(0, 1)


## Get random X,Y click coordinates for button
def get_xy():
    start_pos = [117, 248]
    button_size = [90, 28]
    new_pos = [
        start_pos[0] + random.randint(1, button_size[0]),
        start_pos[1] + random.randint(1, button_size[1])]
    return new_pos


## Custom timestamp format used by FC
def get_timestamp():
    ts = str(int(time.time() * 1000))
    p1 = ts[:7]
    p2 = ts[7:13]
    n = p1 + "00" + p2
    return n


## Canvas fingerprint generator
def get_canvas_fingerprint():
    return random.randint(1424337346, 1428337346) * -1


## Generate font keys
def get_font_keys():
    return "Arial,Arial Black,Arial Narrow,Book Antiqua,Bookman Old Style,Calibri,Cambria,Cambria Math,Century,Century Gothic,Century Schoolbook,Comic Sans MS,Consolas,Courier,Courier New,Garamond,Georgia,Helvetica,Impact,Lucida Bright,Lucida Calligraphy,Lucida Console,Lucida Fax,Lucida Handwriting,Lucida Sans,Lucida Sans Typewriter,Lucida Sans Unicode,Microsoft Sans Serif,Monotype Corsiva,MS Gothic,MS PGothic,MS Reference Sans Serif,MS Sans Serif,MS Serif,Palatino Linotype,Segoe Print,Segoe Script,Segoe UI,Segoe UI Light,Segoe UI Semibold,Segoe UI Symbol,Tahoma,Times,Times New Roman,Trebuchet MS,Verdana,Wingdings,Wingdings 2,Wingdings 3".split(",")


## Generate plugin keys
def get_plugin_keys():
    return "Chrome PDF Plugin,Chrome PDF Viewer,Native Client".split(",")


## Generate jsbd value (time-related)
## Yet to look into how this is actually generated. This is just for quickly fixing
## FunCaptcha's ban on the default jsbd that we had previously
def get_jsbd(browser):
    if browser == "chrome":
        return json.dumps({
            "HL": random.randint(1, 28),
            "NCE": True,
            "DA": None,
            "DR": None,
            "DMT": random.randint(1, 31),
            "DO": None,
            "DOT": random.randint(1, 31)
        }, separators=(',',':'))
    
    elif browser == "firefox":
        return json.dumps({
            "HL": random.randint(1, 12),
            "NCE": True,
            "DMTO": 1,
            "DOTO": 1
        }, separators=(',',':'))
    
    
## Calculate angle from _guiFontColr
def get_rotation_angle(font_clr):
    angle = int(font_clr.replace("#", "")[-3:], 16)
    if angle > 113:
        angle = angle/10
    return angle


## CryptoJS AES Encryption
def cryptojs_encrypt(data, key):
    # Padding
    data = data + chr(16-len(data)%16)*(16-len(data)%16)

    salt = b"".join(random.choice(string.ascii_lowercase).encode() for x in range(8))
    salted, dx = b"", b""
    while len(salted) < 48:
        dx = hashlib.md5(dx+key.encode()+salt).digest()
        salted += dx

    key = salted[:32]
    iv = salted[32:32+16]
    aes = AES.new(key, AES.MODE_CBC, iv)

    encrypted_data = {"ct": base64.b64encode(aes.encrypt(data.encode())).decode("utf-8"), "iv": iv.hex(), "s": salt.hex()}
    return json.dumps(encrypted_data, separators=(',', ':'))


## CryptoJS AES Decryption
def cryptojs_decrypt(data, key):
    data = json.loads(data)
    dk = key.encode()+bytes.fromhex(data["s"])

    md5 = [hashlib.md5(dk).digest()]
    result = md5[0]
    for i in range(1, 3+1):
        md5.insert(i, hashlib.md5((md5[i-1]+dk)).digest())
        result += md5[i]
    
    aes = AES.new(result[:32], AES.MODE_CBC, bytes.fromhex(data["iv"]))
    data = aes.decrypt(base64.b64decode(data["ct"]))
    return data


class FunCaptchaChallenge():
    images = None
    metadata = {}
    
    ## Set up challenge object
    def __init__(self, session, bda, full_token, session_token, region, lang, analytics_tier, predownload_images=True):
        self.session = session
        self.proxy = self.session.proxy
        self.bda = bda
        self.full_token = full_token
        self.session_token = session_token
        self.region = region
        self.lang = lang
        self.analytics_tier = analytics_tier
        self.predownload_images = predownload_images
        self.send_analytics(render_type="canvas", sid=self.region, category="Site URL", analytics_tier=self.analytics_tier, session_token=self.session_token, action=self.session.page_url)
        self.reload(status="init")

    
    ## Reload the challenge
    def reload(self, status):
        ts = get_timestamp()
        r_resp = self.session.r.post(
            url=f"{self.session.service_url}/fc/gfct/",
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "cache-control": "no-cache",
                "X-NewRelic-Timestamp": ts,
                "X-Requested-With": "XMLHttpRequest",
                "X-Requested-ID": self.get_request_id(),
                **self.session.get_additional_browser_headers(),
                "Origin": self.session.service_url, 
                "Referer": self.session.service_url + "/fc/gc"},
            cookies={
                "timestamp": ts},
            data={
                "analytics_tier": self.analytics_tier,
                "render_type": "canvas",
                "lang": self.lang,
                "sid": self.region,
                "token": self.session_token,
                "data[status]": status}).json()

        self.metadata = {}
        self.token = r_resp["challengeID"]
        self.id = r_resp["challengeURL"]
        self.timeout = r_resp["sec"]
        self.angle = get_rotation_angle(r_resp["game_data"]["customGUI"]["_guiFontColr"])
        self.encrypted_mode = bool(r_resp["game_data"]["customGUI"]["encrypted_mode"])
        self.image_urls = r_resp["game_data"]["customGUI"]["_challenge_imgs"]

        if self.image_urls:
            ## Preload images
            if self.predownload_images:
                self.images = list(map(self.download_image, self.image_urls))
            
            self.send_analytics(render_type="canvas", sid=self.region, category="loaded", game_token=self.token, analytics_tier=self.analytics_tier, game_type=1, session_token=self.session_token, action="game loaded")
    
            ## Get encryption key, if needed
            if self.encrypted_mode:
                self.key = self.get_encryption_key()
                self.send_analytics(render_type="canvas", sid=self.region, category="begin app", game_token=self.token, analytics_tier=self.analytics_tier, game_type=1, session_token=self.session_token, action="user clicked verify")
    

    ## Return image count
    def get_image_count(self):
        return len(self.image_urls)


    ## This is some sort of weird metadata that's sent in
    ## the X-Requested-ID header
    def update_metadata(self, origin, value=None):
        if origin == "ekey" and not self.metadata.get("sc"):
            self.metadata["sc"] = get_xy()
        
        elif origin == "guess" and not self.metadata.get("dc"):
            self.metadata["dc"] = get_xy()
        
        elif origin == "lastguess" and value:
            self.metadata["ech"] = "{:.2f}".format(value)
    
    
    ## Send analytics logging request
    def send_analytics(self, **kwargs):
        ts = get_timestamp()
        an_resp = self.session.r.post(
            url=f"{self.session.service_url}/fc/a/",
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "cache-control": "no-cache",
                "X-NewRelic-Timestamp": ts,
                "X-Requested-With": "XMLHttpRequest",
                "X-Requested-ID": self.get_request_id(),
                **self.session.get_additional_browser_headers(),
                "Origin": self.session.service_url, 
                "Referer": self.session.service_url + "/fc/gc"},
            cookies={
                "timestamp": ts},
            data={
                **kwargs}).json()

        return an_resp.get("logged")
    

    ## Submit guesses
    def submit_guesses(self, guesses):
        data = ",".join(map(lambda x: "{:.2f}".format(x), guesses))
        encrypted_data = cryptojs_encrypt(data, self.session_token)

        if len(guesses) == len(self.image_urls):
            self.update_metadata(origin="lastguess", value=guesses[-1])
        else:
            self.update_metadata(origin="guess")
        
        ts = get_timestamp()
        sg_resp = self.session.r.post(
            url=f"{self.session.service_url}/fc/ca/",
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "cache-control": "no-cache",
                "X-NewRelic-Timestamp": ts,
                "X-Requested-With": "XMLHttpRequest",
                "X-Requested-ID": self.get_request_id(),
                **self.session.get_additional_browser_headers(),
                "Origin": self.session.service_url, 
                "Referer": self.session.service_url + "/fc/gc"},
            cookies={
                "timestamp": ts},
            data={
                "game_token": self.token,
                "session_token": self.session_token,
                "sid": self.region,
                "guess": encrypted_data,
                "analytics_tier": self.analytics_tier}).json()
        
        ## Update encryption key if response contains one
        if "decryption_key" in sg_resp:
            self.key = sg_resp["decryption_key"]
        
        ## Return status of challenge
        return sg_resp.get("solved")


    ## Download image data from url
    def download_image(self, image_url):
        i_resp = self.session.r.get(
            url=image_url,
            headers={
                "Referer": f"{self.session.service_url}/fc/apps/canvas/{self.id}/?meta=6"})
        return i_resp.content
    

    ## Get encryption key for the first image
    def get_encryption_key(self):
        self.update_metadata(origin="ekey")

        ts = get_timestamp()
        ek_resp = self.session.r.post(
            url=f"{self.session.service_url}/fc/ekey/",
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "cache-control": "no-cache",
                "X-NewRelic-Timestamp": ts,
                "X-Requested-With": "XMLHttpRequest",
                "X-Requested-ID": self.get_request_id(),
                **self.session.get_additional_browser_headers(),
                "Origin": self.session.service_url, 
                "Referer": f"{self.session.service_url}/fc/gc"},
            cookies={
                "timestamp": ts},
            data={
                "game_token": self.token,
                "sid": self.region,
                "session_token": self.session_token}).json()
        
        return ek_resp["decryption_key"]
    

    ## Generates value for X-Requested-ID header
    def get_request_id(self):
        key = "REQUESTED" + self.session_token + "ID"
        data = json.dumps(self.metadata, separators=(',', ':'))
        return cryptojs_encrypt(data, key)


    def get_iter(self):
        guesses = []
        images_enabled = self.predownload_images
        for img_data in self.images or self.image_urls:
            if not images_enabled:
                img_data = self.download_image(img_data)
            img_data = cryptojs_decrypt(img_data, self.key)
            img = Image.open(BytesIO(img_data))
            def submit(guess):
                guesses.append(guess)
                return self.submit_guesses(guesses)
            yield img, submit


def get_browser_name(user_agent):
    browser_name = httpagentparser.detect(user_agent)["browser"]["name"].lower().strip()
    return browser_name


class FunCaptchaSession:
    ## Set up session object
    def __init__(self, public_key, service_url, page_url, user_agent=DEFAULT_USER_AGENT, proxy=None, predownload_images=True, verify=True, timeout=15):
        self.public_key = public_key
        self.service_url = service_url.rstrip("/")
        self.page_url = page_url.rstrip("/")
        self.site_url = "https://" + urlsplit(self.page_url).netloc
        self.user_agent = user_agent
        self.browser = get_browser_name(self.user_agent)
        self.predownload_images = predownload_images

        ## Create and set-up requests.Session() object
        self.r = requests.session()
        self.proxy = proxy
        if proxy: self.r.proxies = {"http": proxy, "https": proxy}
        self.r.timeout = timeout
        self.r.headers["User-Agent"] = self.user_agent
        self.r.headers["Accept"] = "*/*"
        self.r.headers["Accept-Language"] = "en-US,en;q=0.5"
        self.r.headers["Accept-Encoding"] = "gzip, deflate, br"

        ## Disable SSL validation (for debugging)
        if not verify:
            self.r.verify = False
            requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
    

    ## Get base64-encoded JSON string of browser data for identification
    def get_browser_data(self):
        ## Fingerprint
        fonts = get_font_keys()
        plugins = get_plugin_keys()
        canvas_fp = get_canvas_fingerprint()

        fe = [
            ## DoNotTrack flag
            "DNT:" + ("unspecified" if self.browser == "firefox" else "unknown"),
            ## Language
            "L:en-US",
            ## Depth
            "D:24",
            ## Pixel ratio
            "PR:1.100000023841858",
            ## Screen resolution
            "S:1920,1080",
            ## Available screen resolution (browser window size)
            "AS:1920,1040",
            ## Time offset
            "TO:-120",
            ## Session storage enabled
            "SS:true",
            ## Local storage enabled
            "LS:true",
            ## Indexed DB enabled
            "IDB:true",
            ## .addBehaviour enabled - https://docs.microsoft.com/en-us/previous-versions/windows/internet-explorer/ie-developer/platform-apis/ms535922(v%3Dvs.85)
            "B:false",
            ## OpenDB enabled
            "ODB:true",
            ## CPU class
            "CPUC:unknown",
            ## Platform key
            "PK:Win32",
            ## Canvas fingerprint
            "CFP:" + str(canvas_fp),
            ## Has fake resolution
            "FR:false",
            ## Has fake OS
            "FOS:false",
            ## Has fake browser
            "FB:false",
            ## Javascript fonts
            "JSF:" + ",".join(fonts),
            ## Plugin keys
            "P:" + ",".join(plugins),
            ## Touch
            "T:0,false,false",
            ## navigator.hardwareConcurrency value
            "H:8",
            ## Flash enabled
            "SWF:false"]
        
        ## Calculate hashes
        ## I haven't managed to replicate fp hashes yet, so it's just filled with a random value for now
        fp = secrets.token_hex(16)
        ife_hash = mm3js.call("x64hash128", ", ".join(fe), 38) if not USE_FAKE_HASHES else secrets.token_hex(16)

        ## Window hash
        ## This cannot be verified by the server, so it's just a random value for now
        wh = secrets.token_hex(16) + "|" + secrets.token_hex(16)
        
        ## Time/date-related stuff
        jsbd = get_jsbd(self.browser)
        ts = time.time()
        
        ## BDA Data
        data = []
        data.append({"key": "api_type", "value": "js"})
        data.append({"key": "p", "value": 1})
        data.append({"key": "f", "value": fp})
        data.append({"key": "n", "value": base64.b64encode(str(int(ts)).encode("utf-8")).decode("utf-8")})
        data.append({"key": "wh", "value": wh})
        data.append({"value": fe, "key": "fe"}) ## Yes, this is intentional
        data.append({"key": "ife_hash", "value": ife_hash})
        data.append({"key": "cs", "value": 1})
        data.append({"key": "jsbd", "value": jsbd})
    
        ## Calculate encryption key
        timeframe = int(ts - (ts % 21600))
        key = self.user_agent + str(timeframe)

        ## JSON -> AES -> BASE64
        data = json.dumps(data, separators=(',', ':'))
        data = cryptojs_encrypt(data, key)
        data = base64.b64encode(data.encode("utf-8")).decode("utf-8")
        return data


    ## Browsers often have unique headers of their own. This function
    ## aims to include those headers depending on the user agent.
    def get_additional_browser_headers(self):
        if self.browser == "chrome":
            return {
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Dest": "empty"}
        
        elif self.browser == "firefox":
            return {
                "TE": "Trailers"}
        
        return {}


    ## Get new challenge
    def create_new_challenge(self):
        bda = self.get_browser_data()
        rnd = get_float()
        nc_resp = self.r.post(
            url=f"{self.service_url}/fc/gt2/public_key/{self.public_key}",
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": self.site_url,
                **self.get_additional_browser_headers(),
                "Referer": self.page_url},
            data={
                "bda": bda,
                "public_key": self.public_key,
                "site": self.site_url,
                "userbrowser": self.user_agent,
                "simulate_rate_limit": 0,
                "simulated": 0,
                "language": "en",
                "rnd": rnd}).json()

        ## Create FunCaptchaChallenge object based on data
        ## returned by /fc/gc/public_key/{pk}
        full_token = nc_resp["token"]
        data = parse_full_token(full_token)
        return FunCaptchaChallenge(
            session=self,
            bda=bda,
            full_token=full_token,
            session_token=data["token"],
            region=data["r"],
            lang=data["lang"],
            analytics_tier=int(data["at"]),
            predownload_images=self.predownload_images)
