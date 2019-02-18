import re
from urllib.parse import urlparse

from twisted.web.client import getPage
from twisted.internet import reactor,defer
from six.moves.urllib.parse import (urljoin, urlsplit, urlunsplit,
                                    urldefrag, urlencode,
                                    quote, parse_qs, parse_qsl,
                                    ParseResult, unquote, urlunparse)
from w3lib.url import any_to_uri
from w3lib.util import to_bytes, to_native_str, to_unicode
import string

# constants from RFC 3986, Section 2.2 and 2.3
RFC3986_GEN_DELIMS = b':/?#[]@'
RFC3986_SUB_DELIMS = b"!$&'()*+,;="
RFC3986_RESERVED = RFC3986_GEN_DELIMS + RFC3986_SUB_DELIMS
RFC3986_UNRESERVED = (string.ascii_letters + string.digits + "-._~").encode('ascii')
EXTRA_SAFE_CHARS = b'|'  # see https://github.com/scrapy/w3lib/pull/25
_safe_chars = RFC3986_RESERVED + RFC3986_UNRESERVED + EXTRA_SAFE_CHARS + b'%'

def safe_url_string(url, encoding='utf8', path_encoding='utf8'):
    """Convert the given URL into a legal URL by escaping unsafe characters
    according to RFC-3986.

    If a bytes URL is given, it is first converted to `str` using the given
    encoding (which defaults to 'utf-8'). 'utf-8' encoding is used for
    URL path component (unless overriden by path_encoding), and given
    encoding is used for query string or form data.
    When passing an encoding, you should use the encoding of the
    original page (the page from which the URL was extracted from).

    Calling this function on an already "safe" URL will return the URL
    unmodified.

    Always returns a native `str` (bytes in Python2, unicode in Python3).
    """
    # Python3's urlsplit() chokes on bytes input with non-ASCII chars,
    # so let's decode (to Unicode) using page encoding:
    #   - it is assumed that a raw bytes input comes from a document
    #     encoded with the supplied encoding (or UTF8 by default)
    #   - if the supplied (or default) encoding chokes,
    #     percent-encode offending bytes
    parts = urlsplit(to_unicode(url, encoding=encoding,
                                errors='percentencode'))

    # IDNA encoding can fail for too long labels (>63 characters)
    # or missing labels (e.g. http://.example.com)
    try:
        netloc = parts.netloc.encode('idna')
    except UnicodeError:
        netloc = parts.netloc

    # quote() in Python2 return type follows input type;
    # quote() in Python3 always returns Unicode (native str)
    return urlunsplit((
        to_native_str(parts.scheme),
        to_native_str(netloc).rstrip(':'),

        # default encoding for path component SHOULD be UTF-8
        quote(to_bytes(parts.path, path_encoding), _safe_chars),

        # encoding of query and fragment follows page encoding
        # or form-charset (if known and passed)
        quote(to_bytes(parts.query, encoding), _safe_chars),
        quote(to_bytes(parts.fragment, encoding), _safe_chars),
    ))
def escape_ajax(url):
    """
    Return the crawleable url according to:
    https://developers.google.com/webmasters/ajax-crawling/docs/getting-started

    >>> escape_ajax("www.example.com/ajax.html#!key=value")
    'www.example.com/ajax.html?_escaped_fragment_=key%3Dvalue'
    >>> escape_ajax("www.example.com/ajax.html?k1=v1&k2=v2#!key=value")
    'www.example.com/ajax.html?k1=v1&k2=v2&_escaped_fragment_=key%3Dvalue'
    >>> escape_ajax("www.example.com/ajax.html?#!key=value")
    'www.example.com/ajax.html?_escaped_fragment_=key%3Dvalue'
    >>> escape_ajax("www.example.com/ajax.html#!")
    'www.example.com/ajax.html?_escaped_fragment_='

    URLs that are not "AJAX crawlable" (according to Google) returned as-is:

    >>> escape_ajax("www.example.com/ajax.html#key=value")
    'www.example.com/ajax.html#key=value'
    >>> escape_ajax("www.example.com/ajax.html#")
    'www.example.com/ajax.html#'
    >>> escape_ajax("www.example.com/ajax.html")
    'www.example.com/ajax.html'
    """
    defrag, frag = urldefrag(url)
    if not frag.startswith('!'):
        return url
    return add_or_replace_parameter(defrag, '_escaped_fragment_', frag[1:])

def add_or_replace_parameter(url, name, new_value):
    """Add or remove a parameter to a given url

    # >>> import w3lib.url
    # >>> w3lib.url.add_or_replace_parameter(https', 'arg', 'v')
    # 'https://www.example.com/index.php?arg=v'
    # >>> w3lib.url.add_or_replace_parameter(hhttps, 'arg4', 'v4')
    # 'http://www.example.com/index.php?arg1=v1&arg2=v2&arg3httpsarg4=v4'
    # >>> w3lib.url.add_or_replace_parameter(https, 'arg3', 'v3new')
    # 'http://www.example.com/inhttpsphp?arg1=v1&arg2=v2&arg3=v3new'
    # >>>

    """
    parsed = urlsplit(url)
    args = parse_qsl(parsed.query, keep_blank_values=True)

    new_args = []
    found = False
    for name_, value_ in args:
        if name_ == name:
            new_args.append((name_, new_value))
            found = True
        else:
            new_args.append((name_, value_))

    if not found:
        new_args.append((name, new_value))

    query = urlencode(new_args)
    return urlunsplit(parsed._replace(query=query))

def add_http_if_no_scheme(url):
    """Add http as the default scheme if it is missing from the url."""
    match = re.match(r"^\w+://", url, flags=re.I)
    if not match:
        parts = urlparse(url)
        scheme = "http:" if parts.netloc else "http://"
        url = scheme + url

    return url


def guess_scheme(url):
    """Add an URL scheme if missing: file:// for filepath-like input or http:// otherwise."""
    parts = urlparse(url)
    if parts.scheme:
        return url
    # Note: this does not match Windows filepath
    if re.match(r'''^                   # start with...
                    (
                        \.              # ...a single dot,
                        (
                            \. | [^/\.]+  # optionally followed by
                        )?                # either a second dot or some characters
                    )?      # optional match of ".", ".." or ".blabla"
                    /       # at least one "/" for a file path,
                    .       # and something after the "/"
                    ''', parts.path, flags=re.VERBOSE):
        return any_to_uri(url)
    else:
        return add_http_if_no_scheme(url)

def validate_url(url):
    _url = urlparse(url)
    print(_url)
    if not _url.scheme :
        if not _url.netloc:
            return False
        elif re.match(r'''^                   # start with...
                            (
                                \.              # ...a single dot,
                                (
                                    \. | [^/\.]+  # optionally followed by
                                )?                # either a second dot or some characters
                            )?      # optional match of ".", ".." or ".blabla"
                            /       # at least one "/" for a file path,
                            .       # and something after the "/"
                            ''', _url.path, flags=re.VERBOSE):
            return any_to_uri(url)
        else:
            return add_http_if_no_scheme(url)
    return url



#
# dd = validate_url('www.baidu.com')
# print(dd)


