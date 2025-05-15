import io
import json
import logging
import os
import re
import time
from urllib.parse import parse_qsl, urlencode, urlparse

import backend.sqlite
import oauth2 as oauth
import requests
from backend.common import Bookmark, Document
from bs4 import BeautifulSoup
from ebooklib import epub
from flask import Flask, jsonify, request, send_file
from my_secrets import oauth_creds
from PIL import Image
from werkzeug.middleware.proxy_fix import ProxyFix

config = {
    "DEBUG": False,          # some Flask specific configs
}

app = Flask(__name__)
app.config.from_mapping(config)
app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)
app.logger.setLevel(logging.INFO)


BASE_URL = "https://www.instapaper.com"
API_VERSION = "/api/1"

consumer = oauth.Consumer(
    oauth_creds['key'], oauth_creds['secret'])
client = oauth.Client(consumer)

try:
    with open("domain_map.json") as fh:
        domain_map = json.load(fh)
except:
    domain_map = {}
app.logger.debug(f"domain_map: {domain_map}")


@app.route("/")
def hello_world():
    return "Here there be dragons."


@app.post("/oauth/v2/token")
def get_token():
    params = json.loads(request.get_data())
    app.logger.info(f"Logging in {params['username']}")
    access_token_url = f"{BASE_URL}{API_VERSION}/oauth/access_token"
    response, content = client.request(access_token_url, "POST", urlencode({
        'x_auth_mode': 'client_auth',
        'x_auth_username': params['username'],
        'x_auth_password': params['password']}))
    if response.status == 200:
        return jsonify({"expires_in": 1800,
                        "scope": None,
                        "access_token": content.decode('utf-8')
                        }), 200
    else:
        return "Unauthorized", 401


@app.route("/api/entries.json", methods=["GET", "POST"])
def get_entries():
    global g_storage_backend
    if request.method == "POST":
        url = request.get_json().get("url")
        if url:
            result = get_api_data("/bookmarks/add",
                                  parameters={"url": url})
            app.logger.info(f"Adding URL {url}: {result}")
            return jsonify(result[0])
    else:
        if int(request.args.get('page', 1)) > 1:
            return "only one page plz", 404
        entries = []
        app.logger.debug("get entries")
        instapaper = get_api_data(
            "/bookmarks/list",
            parameters={"limit": request.args.get('perPage', 30)})
        for mark in instapaper:
            if mark['type'] != "bookmark":
                continue
            mark['tags'] = [x['name'] for x in mark['tags']]
            mark['id'] = mark['bookmark_id']
            del mark['bookmark_id']
            del mark['type']
            mark['mimetype'] = "text/html"
            # TODO
            # mark['updated_at'] = parse_somehow_mumble(mark['time']) like :   "updated_at": "2023-01-24T15:21:09+0000",
            bookmark = Bookmark(int(mark['id']), mark['title'], mark['url'], ",".join(mark['tags']))
            app.logger.debug(f"Bookmark: {bookmark.title}")
            g_storage_backend.update_bookmark(bookmark)
            entries.append(mark)
        return jsonify({"_embedded": {"items": entries}}), 200


@app.route("/api/entries/<int:id>.json", methods=['PATCH', 'DELETE'])
def archive_article(id):
    if request.method == "PATCH":
        if request.get_json().get("archive") != 1:
            return jsonify({}), 200
    app.logger.info(f"Archiving {id}")
    get_api_data("/bookmarks/update_read_progress",
                 parameters={"bookmark_id": id,
                             "progress": 1,
                             "progress_timestamp": int(time.time())})
    get_api_data(f"/bookmarks/archive",
                 parameters={"bookmark_id": id})
    return jsonify({"id": id, "archive": 1}), 200


@app.post("/api/entries/<int:id>/tags.json")
def post_tags(id):
    app.logger.warning(f"Tagging NOP for {id}")
    return jsonify({})


@app.route("/api/entries/<int:id>/export.epub", methods=['GET', 'HEAD'])
def get_epub(id):
    global g_storage_backend
    if os.path.exists(f"/tmp/{id}.epub"):
        if request.method == "HEAD":
            return jsonify({"id": id}, 200)
        return send_file(
            f"/tmp/{id}.epub",
            mimetype='application/epub+zip'
        ), 200

    page_content = get_api_data("/bookmarks/get_text",
                                parameters={"bookmark_id": id})
    if not page_content:
        return "No content?", 500
    mark = g_storage_backend.get_bookmark(id)
    app.logger.info(f"Building epub for {id}: {mark.title}")
    if not mark:
        get_entries()
        mark = g_storage_backend.get_bookmark(id)
    if not mark:
        return "No article?", 500
    app.logger.debug(f"mark: {mark}")
    r_data = {}
    if mark.url.startswith('http'):
        app.logger.debug(f"enriching {id} with readable data")
        try:
            r_data = requests.post(
                'http://postlight:3000/parse-html', json={'url': mark.url}).json()
            for k in ['content', 'title', 'dek', 'next_page_url', 'url', 'message']:
                try:
                    r_data.pop(k)
                except:
                    pass
        except Exception as e:
            app.logger.warning(f"couldn't enrich {mark.title} with postlight: {e}")
            pass
    else:
        r_data['author'] = "email"
    r_data.update(mark.__dict__)
    author = None
    if 'author' in r_data:
        author = r_data['author']
    elif 'domain' in r_data:
        author = domain_map.get(r_data['domain'], r_data['domain'])
    if not author:
        author = ""
    title = r_data.get('title', "No Title")
    header_line = ""
    author_line = ""
    if r_data.get('url', "").startswith("http"):
        domain = r_data['url'].split("/")[2].replace("www.", "", 1)
        domain = domain_map.get(domain, domain)
        header_line += f'<a href="{r_data.get("url", "")}">{domain}</a>'
        author_line = domain
    if author:
        if header_line:
            header_line += " &middot; "
        header_line += f"by {author}"
        if author_line:
            author_line = f"{author} for {author_line}"
        else:
            author_line = author
    page_content = f'<h1>{title}</h1><div>{header_line}</div>\n' + page_content
    book = epub.EpubBook()
    chapters = []
    book.set_title(r_data['title'])
    book.add_author(author_line)
    chapter = epub.EpubHtml(
        uid="0", title=r_data['title'], file_name=f"0.xhtml")
    chapter.content = '<html><head>' + \
        '<link rel="stylesheet" href="style/default.css" />' + \
        '</head><body>' + \
        page_content + \
        '</body></html>'
    book.add_item(chapter)
    chapters.append(chapter)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    with open("nook-glowlight-3.css") as f:
        nav_css = epub.EpubItem(
            uid="style_nav", file_name="style/default.css",
            media_type="text/css", content=f.read())
    book.add_item(nav_css)
    book.spine = chapters

    IMAGE_GREYSCALE = True

    # Maximum dimensions of embedded images
    IMAGE_MAX_SIZE = (1000, 1000)

    # now cache images into the book
    for item in book.items:
        if type(item) is not epub.EpubHtml:
            continue
        soup = BeautifulSoup('<html><body>%s</body></html>' %
                             item.content, 'html5lib')
        image_names = set()
        img_count = 0
        for img in soup.find_all('img'):
            src = img.get('src')

            # Remove junk images
            if not src or "_noimg" in mark.tags:
                img.decompose()
                continue
            if src.startswith('denied:'):
                img.decompose()
                continue
            if src.startswith('data:'):
                img.decompose()
                continue
            img_count += 1
            if img_count > 25:
                break
            src_parts = urlparse(src)
            ext = os.path.splitext(src_parts.path)[1]
            name = str(hash(src)) + ext

            if name not in image_names:
                # Create `EpubImage` wrapper object
                image = epub.EpubImage()
                image.id = str(hash(src))
                image.file_name = name

                thumbnail = io.BytesIO()

                img['src'] = re.sub("%2C$", "", img['src'])
                try:
                    app.logger.debug(f"Downloading image {img['src']}")
                    content = requests.get(
                        img['src'], timeout=3.05).content
                except (requests.exceptions.ContentDecodingError,
                        requests.exceptions.ConnectionError,
                        requests.exceptions.ReadTimeout,
                        requests.exceptions.InvalidSchema,
                        requests.exceptions.MissingSchema) as e:
                    app.logger.warning('ERROR: Skipping image %s (%s)' %
                                       (img['src'], e))
                    continue

                original = io.BytesIO()
                original.write(content)

                try:
                    # Create smaller, greyscale image from source image
                    # convert to `RGBA` before `L` or Pillow will complain
                    im = Image.open(original).convert('RGBA')
                    im.thumbnail(IMAGE_MAX_SIZE)
                    if IMAGE_GREYSCALE:
                        im = im.convert('L')
                    im.save(thumbnail, 'png' if ext == '.png' else 'jpeg')

                except OSError as e:
                    app.logger.warning('Skipping image %s (%s)' %
                                       (img['src'], e))
                    continue

                thumbnail.seek(0)

                image.content = thumbnail.read()
                book.add_item(image)
                image_names.add(name)

            img['style'] = 'max-width: 100%'
            img['src'] = name
        item.content = str(soup.body)
    try:
        epub.write_epub(f"/tmp/{r_data['id']}.epub", book)
    except:
        return f"Cannot build epub for {id}", 500

    if request.method == "HEAD":
        return jsonify({"id": id}, 200)
    return send_file(
        f"/tmp/{r_data['id']}.epub",
        mimetype='application/epub+zip'
    ), 200


def get_api_data(url, parameters={}):
    token = request.headers['Authorization'].split(" ", 2)[1]
    token = dict(parse_qsl(token))
    token = oauth.Token(token.get("oauth_token"),
                        token.get('oauth_token_secret'))
    http = oauth.Client(consumer, token)
    response, data = http.request(
        f"{BASE_URL}{API_VERSION}{url}", "POST", urlencode(parameters))
    if response.get("status") == '200':
        try:
            return json.loads(data.decode())
        except Exception as e:
            return data.decode()
    return {}

# # # PROGRESS SYNC CODE


@app.route('/users/create', methods=['POST'])
def register():
    global g_storage_backend

    if not g_allow_registration:
        return "Registration has been disabled", 400

    if not request.is_json:
        return "Invalid Request", 400

    j = request.get_json()
    username = j.get("username")
    userkey = j.get("password")
    app.logger.warning(f"CREATING NEW SYNC USER {username}")

    # Check that they're both present
    if (not username) or (not userkey):
        return "Invalid Request", 400
    if not g_storage_backend.create_user(username, userkey):
        return "Username is already registered", 409

    # Return the created username
    return jsonify(dict(username=username)), 201


@app.route('/users/auth')
def authorize():
    global g_storage_backend

    username = request.headers.get("x-auth-user")
    userkey = request.headers.get("x-auth-key")
    app.logger.info(f"Logging in sync user {username}")

    # Check that they're both present
    if (not username) or (not userkey):
        return "Invalid Request", 400

    if g_storage_backend.check_login(username, userkey):
        # Success
        return jsonify(dict(authorized="OK"))
    # Access Denied
    return "Incorrect username or password.", 401


@app.route('/syncs/progress', methods=['PUT'])
def sync_progress():
    global g_storage_backend

    if not request.is_json:
        return "Invalid Request", 400

    j = request.get_json()
    if not j:
        return "Invalid JSON Data", 400

    username = request.headers.get("x-auth-user")
    userkey = request.headers.get("x-auth-key")
    document = j.get("document")
    progress = j.get("progress")
    percentage = j.get("percentage")
    device = j.get("device")
    device_id = j.get("device_id")
    timestamp = int(time.time())
    app.logger.info(
        f"Syncing for {username}: {document} {int(percentage * 100)}%")

    if ((username is None) or (document is None) or (progress is None) or (percentage is None)
       or (userkey is None) or (device is None) or (device_id is None) or (timestamp is None)):
        return "Missing/invalid parameters provided", 400

    # Let's authenticate first
    if not g_storage_backend.check_login(username, userkey):
        return "Incorrect username or password.", 401

    # Create a document based on all of the provided paramters
    doc = Document(document, progress, percentage,
                   device, device_id, timestamp)

    # Add the document to the database
    g_storage_backend.update_document(username, doc)

    return jsonify(dict(document=document, timestamp=timestamp))


@app.route('/syncs/progress/<document>')
def get_progress(document):
    global g_storage_backend

    username = request.headers.get("x-auth-user")
    userkey = request.headers.get("x-auth-key")
    # Let's authenticate first
    if not g_storage_backend.check_login(username, userkey):
        return "Incorrect username or password.", 401

    # Get the document
    doc = g_storage_backend.get_document(username, document)
    if doc is None:
        return "Document does not exist", 404
    app.logger.info(
        f"Getting sync for {username}: {document} {int(doc.percentage * 100)}%")
    # Return it to the client
    return jsonify(doc), 200


def initialize():
    # Set some global configuration variables
    if "KOSYNC_SQLITE3_DB" in os.environ:
        db = os.environ["KOSYNC_SQLITE3_DB"]
    else:
        db = "./data/sqlite3.db"

    global g_allow_registration
    g_allow_registration = True
    if ("KOSYNC_SQLITE3_DB" in os.environ) and (os.environ["KOSYNC_SQLITE3_DB"] == "false"):
        g_allow_registration = False

    # Initialize the database
    global g_storage_backend
    g_storage_backend = backend.sqlite.BackendSQLite(db)


initialize()

# # # END PROGRESS SYNC CODE


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=8081)
