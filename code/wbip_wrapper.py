import io
import json
import os
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
    "DEBUG": True,          # some Flask specific configs
    "CACHE_TYPE": "SimpleCache",  # Flask-Caching related configs
    "CACHE_DEFAULT_TIMEOUT": 300
}

app = Flask(__name__)
app.config.from_mapping(config)
app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)


BASE_URL = "https://www.instapaper.com"
API_VERSION = "/api/1"

consumer = oauth.Consumer(
    oauth_creds['key'], oauth_creds['secret'])
client = oauth.Client(consumer)


@app.route("/")
def hello_world():
    return "Here there be dragons."


@app.post("/oauth/v2/token")
def get_token():
    params = json.loads(request.get_data())
    access_token_url = f"{BASE_URL}{API_VERSION}/oauth/access_token"
    response, content = client.request(access_token_url, "POST", urlencode({
        'x_auth_mode': 'client_auth',
        'x_auth_username': params['username'],
        'x_auth_password': params['password']}))
    if response.status == 200:
        return jsonify({"expires_in": 360, "scope": None, "access_token": content.decode('utf-8')}), 200
    else:
        return "Unauthorized", 401


@app.route("/api/entries.json", methods=["GET", "POST"])
def get_entries():
    global g_storage_backend
    if request.method == "POST":
        url = request.get_json().get("url")
        if url:
            result = get_api_data("/bookmarks/add", request.headers['Authorization'],
                                  parameters={"url": url})
            app.logger.info(f"Adding URL {url}: {result}")
            return jsonify(result[0])
    else:
        if int(request.args.get('page', 1)) > 1:
            return "only one page plz", 404
        entries = []
        app.logger.info("get entries")
        instapaper = get_api_data("/bookmarks/list", request.headers['Authorization'],
                                  parameters={"limit": request.args.get('perPage', 30)})
        for mark in instapaper:
            if mark['type'] != "bookmark":
                continue
            mark['tags'] = []
            mark['id'] = mark['bookmark_id']
            del mark['bookmark_id']
            del mark['type']
            mark['mimetype'] = "text/html"
            # TODO
            # mark['updated_at'] = parse_somehow_mumble(mark['time']) like :   "updated_at": "2023-01-24T15:21:09+0000",
            bookmark = Bookmark(int(mark['id']), mark['title'], mark['url'])
            app.logger.info(f"Bookmark: {bookmark.title}")
            g_storage_backend.update_bookmark(bookmark)
            entries.append(mark)
        return jsonify({"_embedded": {"items": entries}}), 200


@app.route("/api/entries/<int:id>.json", methods=['PATCH', 'DELETE', 'GET'])
def archive_article(id):
    archive = False
    if request.method == "PATCH":
        if request.get_json().get("archive") == 1:
            archive = True
    elif request.method == "DELETE":
        archive = True
    # elif request.method == "GET":
    #     mark = cache.get(str(id))
    #     mark['content'] = get_api_data("/bookmarks/get_text", request.headers['Authorization'],
    #                                    parameters={"bookmark_id": id})
    #     return jsonify(mark)
    if archive:
        get_api_data(f"/bookmarks/archive", request.headers['Authorization'],
                     parameters={"bookmark_id": id})
        return jsonify({"id": id, "archive": 1}), 200
    return jsonify({}), 200


@app.post("/api/entries/<int:id>/tags.json")
def post_tags(id):
    return jsonify({})


@app.get("/api/entries/<int:id>/export.epub")
def get_epub(id):
    global g_storage_backend
    page_content = get_api_data("/bookmarks/get_text", request.headers['Authorization'],
                                parameters={"bookmark_id": id})
    if not page_content:
        return "No content?", 500
    retry_count = 0
    mark = g_storage_backend.get_bookmark(id)
    if not mark:
        get_entries()
        mark = g_storage_backend.get_bookmark(id)
    if not mark:
        return "No article?", 500
    app.logger.debug(f"mark: {mark}")
    if mark.url.startswith('http'):
        app.logger.debug(f"enriching {id} with readable data")
        r_data = requests.post(
            'https://jduqg3rqm9.execute-api.us-east-1.amazonaws.com/dev/parse-html', json={'url': mark.url}).json()
        for k in ['content', 'title', 'dek', 'next_page_url', 'url', 'message']:
            try:
                r_data.pop(k)
            except:
                pass
        r_data['url'] = mark.url
        r_data['title'] = mark.title
        r_data['id'] = mark.id
        app.logger.debug(json.dumps(r_data))
    author = None
    if 'author' in r_data:
        author = r_data['author']
    elif 'domain' in r_data:
        author = r_data['domain']
    if not author:
        author = ""
    title = r_data.get('title', "No Title")
    cover = r_data.get("lead_image_url")
    header_line = ""
    author_line = ""
    if r_data.get('url', "").startswith("http"):
        domain = r_data['url'].split("/")[2].replace("www.", "", 1)
        header_line += f'<a href="{r_data.get("url", "")}">{domain}</a>'
        author_line = domain
    if author:
        if header_line:
            header_line += " &middot; "
        header_line += f"by {author}"
        author_line = f"{author} for {author_line}"
    page_content = f'<h1>{title}</h1><div>{header_line}</div>\n' + page_content
    # app.logger.debug(page_content)
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
    # book.spine = ['nav'] + chapters
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
            if not src:
                img.decompose()
                continue
            if src.startswith('denied:'):
                img.decompose()
                continue
            if src.startswith('data:'):
                img.decompose()
                continue
            img_count += 1
            if img_count > 10:
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

                try:
                    app.logger.info(f"Downloading image {img['src']}")
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

    epub.write_epub(f"/tmp/{r_data['id']}.epub", book, {})

    return send_file(
        f"/tmp/{r_data['id']}.epub",
        mimetype='application/epub+zip'
    ), 200


def get_api_data(url, auth_header, parameters={}):
    _, token = auth_header.split(" ", 2)
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
    app.run(debug=False, host='0.0.0.0', port=8081)
