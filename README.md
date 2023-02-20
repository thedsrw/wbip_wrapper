# Wallabag Instapaper Wrapper

**Read your Instapaper articles in KOReader**

This container serves a Python Flask app that emulates just enough of the [Wallabag API](https://app.wallabag.it/api/doc) and proxies 
it in to [Instapaper](https://www.instapaper.com/) for use with the [KOReader](http://koreader.rocks) [Wallabag plugin](https://github.com/koreader/koreader/wiki/Wallabag).

## Usage
0. Have a running docker setup.
1. Clone the repo
  ```
  $ git clone git@github.com:thedsrw/wbip_wrapper.git
  ```
2. Make a data directory:
  ```
  $ cd wbip_wrapper
  $ mkdir data
  ```
3. Store your [Instapaper API credentials](https://www.instapaper.com/main/request_oauth_consumer_token) in `code/my_secrets.py` like this:
  ```python
  oauth_creds = {
      "key": "0123456789abcdef0123456789abcdef",
      "secret": "0123456789abcdef0123456789abcdef"
  }
  ```
4. Launch your container!
  ```
  $ docker-compose up
  ```
5. Configure the [KOReader plugin](https://github.com/koreader/koreader/wiki/Wallabag)
   * You should front this container with a webserver running SSL. I use Apache, lets encrypt and mod_proxy, but anything works here. Use this URL in the configuration in KOReader.
   * Generally follow the [KOReader instructions](https://github.com/koreader/koreader/wiki/Wallabag)
   * Because the Client ID and Secret are stored in the container, you skip these in the KOReader plugin - they are ignored. My devices just have 'X' here.

6. **OR** reach out to _dlg_ on the [MobileRead Forums](https://www.mobileread.com), you can try their server and see if it works for you.

## Thank You
The code that builds the ePubs was taken from [Jacob Budin's Portable Wisdom](https://github.com/jacobbudin/portable-wisdom)

This is _also_ a KOReader sync server, because I hope someday to pass KOReader's progress state back to Instapaper (and vice versa?)... 
That code is a direct copy of [Ryan El Kochta's version of koreader-sync](https://github.com/relkochta/koreader-sync)

Thank you.
