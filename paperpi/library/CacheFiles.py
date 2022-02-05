#!/usr/bin/env python3
# coding: utf-8






import logging
from pathlib import Path
import tempfile
import shutil
import requests
import time






logger = logging.getLogger(__name__)






class CacheFiles:
    def __repr__(self):
        return f'CacheFiles({self.path})'
    
    def __str__(self):
        return f'{str(self.path)}'
    
    def __init__(self, path=None, path_prefix=None):
        self.path_prefix = path_prefix
        self.path = path
        
    
    @property
    def path(self):
        '''path to file cache
            if no path is provided /tmp/ will be used
        
        Args:
            path(None or `str`): None(default) or /full/path/to/file_cache/'''
        if isinstance(self._path, tempfile.TemporaryDirectory):
            return Path(self._path.name)
        elif isinstance(self._path, Path):
            return str(self._path.absolute())
        else:
            return str(self._path)

    @path.setter
    def path(self, path):
        if path:
            self._path = Path(path)
        else:
            self._path = tempfile.TemporaryDirectory(prefix=self.path_prefix)        

    @property
    def path_prefix(self):
        '''prefix to use when setting a cache path in /tmp
            prefixes will always be suffixed with "_" to make more readable
        
        Args:
            prefix(`str`): prefix-to-append; '''
        return self._path_prefix
    
    @path_prefix.setter
    def path_prefix(self, path_prefix):
        if not path_prefix:
            self._path_prefix = ''  
        elif path_prefix.endswith('_'):
            self._path_prefix = path_prefix
        else:
            self._path_prefix = path_prefix+'_'
    
    def cleanup(self):
        '''recursively remove all cached files and cache path'''
        logger.debug(f'attempting to clean temporary files: {self._path}')
        if isinstance(self._path, tempfile.TemporaryDirectory):
            self._path.cleanup()
        
        elif isinstance(self._path, Path):
            shutil.rmtree(self._path)
        else:
            logger.warning(f'no cleanup method for this datatype: {type(self.path)}')
    
    def cache_file(self, url, file_id, force=False):
        '''download a remote file and return the local path to the file
            if a local file with the same name is found, download is skipped and path returned
        
        Args:
            url(`str`): url to remote file
            file_id(`str`): path and name to use for local file 
                * `124353465Hb7Asr33v` <- cached in root of cache
                * `LMS_artwork/12Hb2455slqrp.jpg`) <- cached in LMS_artwork/ within cache
            force(`bool`): force a download ignoring local files with the same name'''
        file_id = str(file_id)
        local_file = Path(self.path/file_id).absolute()
        
        logger.debug(f'caching file from url {url} to {local_file}')
        
        if local_file.exists() and force is False:
            logger.debug(f'file previously cached')
            return local_file
        else:
            local_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            r = requests.get(url, stream=True)
        except requests.exceptions.RequestException as e:
            logger.error(f'failed to fetch file at: {url} with error: {e}')
            return None
        
        if r.status_code == 200:
            logger.debug(f'writing file to file {local_file}')
            
            try:
                with open(local_file, 'wb') as file:
                    shutil.copyfileobj(r.raw, file)
            except FileNotFoundError as e:
                logger.warning(f'cache directory "{self.path}" is missing; recreating')
                try:
                    self.path.mkdir()
                    return self.cache_file(url, file_id)
                except Exception as e:
                    logger.error(f'could not create "{self.path}"')
            except (OSError, ValueError) as e:
                logger.error(f'failed to write {local_file}: {e}')
                logger.error(f'{type(e)}')
                return None
            except (FileExistsError) as e:
                logger.warning(f'file "{local_file}" appears to exist already; no action taken')
                return local_file
        else:
            logger.error(f'failed to fetch file at {url} with response code: {r.status_code}')
            return None
            
        return local_file

    def remove_stale(self, d=0, h=0, m=0, s=0, path='./', force=False):
        '''remove stale items from the cache based on modification time in seconds

        Args:
            d, h, m, s (int): days, hours, minutes, seconds
                items older than d:h:m:s will be removed
            path('str'): path within cache to expire items from (default is `./`)

        Returns:
            list: list of files removed
        '''
        def time_to_seconds(d=0, h=0, m=0, s=0):
            total = d * 86400
            total += h * 3600
            total += m * 60
            total += s
            return total    


        expire = []
        expire_time = time_to_seconds(d, h, m, s)
        
        logger.info(f'removing stale files in {self.path/path} older than {expire_time} seconds')
        if expire_time < 1 and not force:
            logger.warning(f'use `force=True` to expire all files in {self.path/path} older than {expire_time} seconds')
        for file in Path(self.path/path).glob('*'):
            if not file.is_file():
                continue
            age = time.time() - file.stat().st_mtime
            if age > time_to_seconds(d, h, m, s):
                expire.append(file)

        expire.sort()
        logger.debug(f'located {len(expire)} files to expire')
        for file in expire:
            try:
                logger.debug(f'removing: {file}')
                file.unlink()
            except FileNotFoundError:
                pass
            except Exception as e:
                logger.warning(f'could not remove file in cache: {file}; {e}')

        return expire                






def main():
    '''demo'''
    logging.basicConfig(level=logging.DEBUG)
    cache = CacheFiles(path_prefix='demo_')
    print(f'created a cache directory: {cache}')
    file = cache.cache_file('https://en.wikipedia.org/static/images/project-logos/enwiki-2x.png', 'wiki_logo.png')
    print(f'cached a file: {file}')
    print(f'downloading the same file again...')
    file = cache.cache_file('https://en.wikipedia.org/static/images/project-logos/enwiki-2x.png', 'wiki_logo.png')
    print('cleaning up cache directory now...')
    cache.cleanup()






if __name__ == "__main__":
    main()


