from __future__ import print_function

import requests
import yaml
import os
import glob
import shutil
import tempfile
import urllib
from depsolver.version import Version
from depsolver.errors import InvalidVersion
from depsolver import PackageInfo, Repository
from devassistant import dapi
from devassistant.dapi import dapver
from devassistant.logger import logger
import sys
import logging
import hashlib
try:
    from yaml import CLoader as Loader
except:
    from yaml import Loader
from devassistant.settings import DAPI_DEFAULT_API_URL
from devassistant.settings import DAPI_DEFAULT_USER_INSTALL
from devassistant.settings import DAPI_DEFAULT_ROOT_INSTALL


class DapVersion(Version):
    '''Version class wrapper for depsolver'''
    @classmethod
    def from_string(cls, version):
        if dapi.Dap._meta_valid['version'].match(version):
            return cls(version)
        raise InvalidVersion("Invalid dap version : '%s'" % version)

    def __init__(self, version):
        self.version = version

    def __str__(self):
        return self.version

    def __hash__(self):
        return hash(str(self))

    def __cmp__(self, other):
        return dapver.compare(str(self), str(other))


    def __eq__(self, other):
        return str(self) == str(other)

    def __lt__(self, other):
        return dapver.compare(str(self), str(other)) < 0


def _api_url():
    return os.environ.get('DAPI_API_URL', DAPI_DEFAULT_API_URL)


def _install_path():
    path = os.environ.get('DAPI_INSTALL', None)
    if path:
        if path.endswith('/'):
            return os.path.expanduser(path[:-1])
        return os.path.expanduser(path)
    if os.geteuid() == 0:
        return DAPI_DEFAULT_ROOT_INSTALL
    return os.path.expanduser(DAPI_DEFAULT_USER_INSTALL)


def _process_req_txt(req):
    '''Returns a processed request or raises an exception'''
    if req.status_code == 404:
        return ''
    if req.status_code != 200:
        raise Exception('Response of the server was {code}'.format(code=req.status_code))
    return req.text


def _process_req(req):
    '''Returns a YAML decoded request'''
    return yaml.load(_process_req_txt(req))


def data(link):
    '''Returns a dictionary from requested link'''
    test = os.environ.get('DAPI_FAKE_DATA', None)
    if test is not None:
        return yaml.load(test)
    req = requests.get(link)
    return _process_req(req)


def _paginated(what, page=''):
    '''Returns a dictionary with all <what>, paginated'''
    if page:
        page = '?page={page}'.format(page=page)
    return data(_api_url() + what + '/' + page)


def users(page=''):
    '''Returns a dictionary with all users, paginated'''
    return _paginated('users', page=page)


def metadaps(page=''):
    '''Returns a dictionary with all metadaps, paginated'''
    return _paginated('metadaps', page=page)


def daps(page=''):
    '''Returns a dictionary with all daps, paginated'''
    return _paginated('daps', page=page)


def user(username=''):
    '''Returns a dictionary with all info about a given user'''
    return data(_api_url() + 'users/' + username + '/')


def metadap(name):
    '''Returns a dictionary with all info about a given metadap'''
    return data(_api_url() + 'metadaps/' + name + '/')


def dap(name, version=''):
    '''Returns a dictionary with all info about a given dap'''
    if version:
        name += '-' + version
    return data(_api_url() + 'daps/' + name + '/')


def search(query, page=''):
    '''Returns a dictionary with the search results, paginated'''
    if page:
        page = '&page={page}'.format(page=page)
    return data(_api_url() + 'search/?q=' + query + page)


def _print_dap_with_description(mdap):
    print(mdap['package_name'], end='')
    latest = mdap['latest_stable'] or mdap['latest']
    if latest:
        latest = data(latest)
        print(' - ', end='')
        print(latest['summary'], end='')
    print('')


def print_users(page=''):
    '''Prints a list of users available on Dapi'''
    u = users(page=page)
    try:
        count = u['count']
    except KeyError:
        raise Exception('Page over maximum or other 404 error')
    if not count:
        raise Exception('Could not find any users')
    for user in u['results']:
        print(user['username'], end='')
        if user['full_name']:
            print(' (' + user['full_name'] + ')')
        else:
            print('')
    if u['next']:
        print('There are more users available, paginate by adding page number')


def print_daps(page=''):
    '''Prints a list of metadaps available on Dapi'''
    m = metadaps(page=page)
    if not m and not page:
        print('Could not find any daps')
        return
    for mdap in m['results']:
        _print_dap_with_description(mdap)
    if m['next']:
        print('There are more daps available, paginate by adding page number')


def _get_metadap_dap(name, version=''):
    '''Return data for dap of given or latets version.'''
    m = metadap(name)
    if not m:
        raise Exception('{dap} not found'.format(dap=name))
    if not version:
        d = m['latest_stable'] or m['latest']
        if d:
            d = data(d)
    else:
        d = dap(name, version)
        if not d:
            raise Exception(
                '{dap} doesn\'t have version {version}'.format(dap=name, version=version))
    return m, d


def print_dap(name, version=''):
    '''Prints detail for a particular dap'''
    m, d = _get_metadap_dap(name, version)
    if d:
        _name = m['package_name'] + '-' + d['version']
    else:
        _name = m['package_name']
    print(_name)
    for i in range(0, len(_name)):
        print('=', end='')
    print('\n')
    if d:
        print(d['summary'])
        if d['description']:
            print('')
            print(d['description'])
    else:
        print('{dap} has no versions\n'.format(dap=name))
    for item in 'active average_rank rank_count reports'.split():
        print(item, end=': ')
        print(m[item])
    if d:
        for item in 'license homepage bugreports is_pre is_latest is_latest_stable'.split():
            if (d[item] is not None):
                print(item, end=': ')
                print(d[item])


def print_search(query, page=''):
    '''Prints the results of a search'''
    m = search(query, page=page)
    try:
        count = m['count']
    except KeyError:
        raise Exception('Page over maximum or other 404 error')
    if not count:
        raise Exception('Could not find any daps for your query')
        return
    for mdap in m['results']:
        mdap = mdap['content_object']
        _print_dap_with_description(mdap)
    if m['next']:
        print('There are more daps available, paginate by adding page number')


def get_installed_daps():
    '''Returns a set of all installed daps'''
    g = glob.glob('{d}/meta/*.yaml'.format(d=_install_path()))
    s = set()
    for a in g:
        s.add(a.split('/')[-1][:-len('.yaml')])
    return s


def uninstall_dap(name, confirm=False):
    if name not in get_installed_daps():
        raise Exception(
            'Cannot uninstall {dap}, it is not in {path}'.format(dap=name, path=_install_path()))
    g = ['{d}/meta/{dap}.yaml'.format(d=_install_path(), dap=name)]
    for loc in 'assistants files icons'.split():
        g += glob.glob('{d}/{loc}/*/{dap}.*'.format(d=_install_path(), loc=loc, dap=name))
        g += glob.glob('{d}/{loc}/*/{dap}'.format(d=_install_path(), loc=loc, dap=name))
    for loc in 'snippets doc'.split():
        g += glob.glob('{d}/{loc}/{dap}.yaml'.format(d=_install_path(), loc=loc, dap=name))
        g += glob.glob('{d}/{loc}/{dap}'.format(d=_install_path(), loc=loc, dap=name))
    if confirm:
        print('The following files and directories will be removed:')
        for f in g:
            print('    ' + f)
        ok = raw_input('Is that OK? [y/N] ')
        if ok.lower() != 'y':
            print('Aborting')
            return False
    for f in g:
        try:
            os.remove(f)
        except OSError:
            shutil.rmtree(f)
    return True


def download_dap(name, version='', d='', directory=''):
    '''Download a dap to a given or temporary directory
    Return a path to that file together with information if the directory should be later deleted'''
    if not d:
        m, d = _get_metadap_dap(name, version)
    if directory:
        _dir = directory
    else:
        _dir = tempfile.mkdtemp()
    try:
        url = d['download']
    except TypeError:
        raise Exception('{dap} has no version to download'.format(dap=name))
    filename = url.split('/')[-1]
    path = os.path.join(_dir, filename)
    urllib.urlretrieve(url, path)
    dapisum = d['sha256sum']
    downloadedsum = hashlib.sha256(open(path, 'rb').read()).hexdigest()
    if dapisum != downloadedsum:
        os.remove(path)
        raise Exception('{dap} has incorrect sha256sum (dapi: {dapi}, downloaded: {downloaded})'
                        .format(dap=name, dapi=dapisum, downloaded=downloadedsum))
    return path, not bool(directory)


def install_dap_from_path(path, update=False):
    '''Installs a dap from a given path'''
    will_uninstall = False
    dap_obj = dapi.Dap(path)
    if dap_obj.meta['package_name'] in get_installed_daps():
        if not update:
            raise Exception('Won\'t override already installed dap')
        else:
            will_uninstall = True
    if os.path.isfile(_install_path()):
        raise Exception(
            '{i} is a file, not a directory'.format(i=_install_path()))
    _dir = tempfile.mkdtemp()
    old_level = logger.getEffectiveLevel()
    logger.setLevel(logging.ERROR)
    ok = dap_obj.check()
    logger.setLevel(old_level)
    if not ok:
        raise Exception('The dap you want to install has errors, won\'t do it')
    dap_obj.extract(_dir)
    if will_uninstall:
        uninstall_dap(dap_obj.meta['package_name'])
    _dapdir = os.path.join(_dir, dap_obj.meta['package_name'] + '-' + dap_obj.meta['version'])
    if not os.path.isdir(_install_path()):
        os.makedirs(_install_path())
    os.mkdir(os.path.join(_dapdir, 'meta'))
    os.rename(os.path.join(_dapdir, 'meta.yaml'), os.path.join(_dapdir, 'meta', dap_obj.meta['package_name'] + '.yaml'))
    for f in glob.glob(_dapdir + '/*'):
        dst = os.path.join(_install_path(), os.path.basename(f))
        if os.path.isdir(f):
            if not os.path.exists(dst):
                os.mkdir(dst)
            for src_dir, dirs, files in os.walk(f):
                dst_dir = src_dir.replace(f, dst)
                if not os.path.exists(dst_dir):
                    os.mkdir(dst_dir)
                for file_ in files:
                    src_file = os.path.join(src_dir, file_)
                    dst_file = os.path.join(dst_dir, file_)
                    shutil.copyfile(src_file, dst_file)
        else:
            shutil.copyfile(f, dst)
    try:
        shutil.rmtree(_dir)
    except:
        pass


def get_installed_version_of(name):
    '''Gets the installed version of the given dap or None if not installed'''
    if name not in get_installed_daps():
        return None
    meta = '{d}/meta/{dap}.yaml'.format(d=_install_path(), dap=name)
    with open(meta) as f:
        data = yaml.load(f.read(), Loader=Loader)
    return data['version']

def _get_dependencies_of(name):
    '''Returns list of dependiencies of the given installed dap or None if not installed'''
    if name not in get_installed_daps():
        return None
    meta = '{d}/meta/{dap}.yaml'.format(d=_install_path(), dap=name)
    with open(meta) as f:
        data = yaml.load(f.read(), Loader=Loader)
    try:
        return data['dependencies']
    except KeyError:
        return []

def install_dap(name, version='', update=False):
    '''Install a dap from dapi
    If update is True, it will remove previously installed daps of the same name'''
    m, d = _get_metadap_dap(name, version)
    if update:
        available = d['version']
        current = get_installed_version_of(name)
        if not current:
            raise Exception('Cannot update not yet installed dap')
        if dapver.compare(available, current) < 0:
            raise Exception(
                'Currently installed version {c} is newer than version {a} available on Dapi'
                .format(c=current, a=available))
        if dapver.compare(available, current) == 0:
            raise Exception(
                'Currently installed version {c} is the same as the version available on Dapi'
                .format(c=current))
    path, remove_dir = download_dap(name, d=d)

    install_dap_from_path(path, update=update)

    try:
        if remove_dir:
            shutil.rmtree(os.dirname(path))
        else:
            os.remove(path)
    except:
        pass

def _get_dependency_metadata():
    '''Returns list of strings with dependency metadata from Dapi'''
    link = os.path.join(_api_url(),'meta.txt')
    return list(filter(None, _process_req_txt(requests.get(link)).split('\n')))

def _depsolver_available_repo():
    '''Returns depsolver Repository instance with available packages from Dapi'''
    repo = []
    for pkg in _get_dependency_metadata():
        repo.append(PackageInfo.from_string(pkg.rstrip(), version_factory=DapVersion.from_string))
    return Repository(repo)

def _depsolver_installed_repo():
    '''Returns depsolver Repository instance with installed packages'''
    repo = []
    for dap in get_installed_daps():
        pstring = dap + '-' + get_installed_version_of(dap)
        deps = _get_dependencies_of(dap)
        if deps:
            pstring += '; depends (' + ', '.join(deps) + ')'
        repo.append(PackageInfo.from_string(pstring, version_factory=DapVersion.from_string))
    return Repository(repo)
