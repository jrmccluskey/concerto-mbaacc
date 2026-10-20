# Download helpers for third-party tools. Intentionally free of Kivy and config imports so they can be unit tested.
import hashlib
import os
import re
from urllib.parse import urlparse

import requests

ALLOWED_DOWNLOAD_HOSTS = ('github.com',)
CHUNK_SIZE = 8192


class EtmDownloadError(Exception):
    pass


def _version_key(tag):
    return tuple(int(x) for x in tag[1:].split('.'))


def select_release(releases, exe_name, tag_pattern):
    # Returns (release, asset) for the highest numbered, non-draft, non-prerelease release
    # that contains an asset named exe_name with a published digest.
    if not isinstance(releases, list):
        raise EtmDownloadError('Unexpected response from GitHub.')
    candidates = []
    for release in releases:
        try:
            if release.get('draft') or release.get('prerelease'):
                continue
            tag = release.get('tag_name', '')
            if not re.fullmatch(tag_pattern, tag):
                continue
            for asset in release.get('assets', []):
                if asset.get('name') == exe_name and asset.get('digest'):
                    candidates.append((release, asset))
                    break
        except AttributeError:
            continue
    if not candidates:
        raise EtmDownloadError('No numbered release containing a verified %s was found.' % exe_name)
    return max(candidates, key=lambda c: _version_key(c[0]['tag_name']))


def _parse_digest(digest):
    algo, _, value = digest.partition(':')
    if algo.lower() != 'sha256' or not re.fullmatch(r'[0-9a-fA-F]{64}', value):
        raise EtmDownloadError('Unsupported checksum format: %s' % digest)
    return value.lower()


def _check_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_DOWNLOAD_HOSTS:
        raise EtmDownloadError('Refusing to download from unexpected URL: %s' % url)


def download_etm(dest_dir, releases_api, exe_name, tag_pattern, progress_cb=None, session=None):
    # Downloads the newest numbered release of exe_name into dest_dir and returns the release tag.
    # Raises EtmDownloadError on any failure. There is deliberately no fallback URL.
    if session is None:
        session = requests.Session()

    try:
        resp = session.get(releases_api, timeout=10, headers={'Accept': 'application/vnd.github+json'})
    except requests.exceptions.RequestException as e:
        raise EtmDownloadError('Could not reach GitHub (%s).' % e.__class__.__name__)
    if resp.status_code != 200:
        msg = 'GitHub returned HTTP %s.' % resp.status_code
        if resp.status_code in (403, 429) and resp.headers.get('X-RateLimit-Remaining') == '0':
            msg += ' API rate limit exceeded, please try again later.'
        raise EtmDownloadError(msg)
    try:
        releases = resp.json()
    except ValueError:
        raise EtmDownloadError('Unexpected response from GitHub.')

    release, asset = select_release(releases, exe_name, tag_pattern)
    tag = release['tag_name']
    url = asset.get('browser_download_url', '')
    _check_url(url)
    expected_hash = _parse_digest(asset['digest'])
    expected_size = asset.get('size')

    final_path = os.path.join(dest_dir, exe_name)
    part_path = final_path + '.part'
    hasher = hashlib.sha256()
    received = 0
    try:
        with session.get(url, stream=True, timeout=30) as dl:
            if dl.status_code != 200:
                raise EtmDownloadError('Download failed with HTTP %s.' % dl.status_code)
            with open(part_path, 'wb') as f:
                for chunk in dl.iter_content(chunk_size=CHUNK_SIZE):
                    if not chunk:
                        continue
                    f.write(chunk)
                    hasher.update(chunk)
                    received += len(chunk)
                    if progress_cb:
                        progress_cb(tag, received, expected_size)
        if expected_size is not None and received != expected_size:
            raise EtmDownloadError('Downloaded size (%s) does not match expected size (%s).' % (received, expected_size))
        if hasher.hexdigest() != expected_hash:
            raise EtmDownloadError('Checksum mismatch for downloaded file.')
        os.replace(part_path, final_path)
    except requests.exceptions.RequestException as e:
        _remove_quietly(part_path)
        raise EtmDownloadError('Download interrupted (%s).' % e.__class__.__name__)
    except OSError as e:
        _remove_quietly(part_path)
        raise EtmDownloadError('Could not write file (%s).' % e)
    except EtmDownloadError:
        _remove_quietly(part_path)
        raise
    return tag


def _remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass
