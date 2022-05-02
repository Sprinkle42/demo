import os
import re
import sys

import builder
import setup_env
from utils import check_output_and_logging

class Repository:
    def __init__(self, url):
        raise NotImplemented('Abstract class cannot be used.')

    def download(self, path):
        raise NotImplemented('Abstract class cannot be used.')

    def get_builder(self):
        raise NotImplemented('Abstract class cannot be used.')

    def get_version_list(self):
        raise NotImplemented('Abstract class cannot be used.')
    
    def switch_to_version(self, version):
        raise NotImplemented('Abstract class cannot be used.')

class GithubRepository(Repository):
    def __init__(self, url):
        self.url = url
        self.path = None
        self.version_list = None

    def download(self, path, force_download=False):
        repo_name = self.url.split('/')[-1]
        if not repo_name.endswith('.git'):
            raise AttributeError('Git url should ends with .git')
        repo_dir = '.'.join(repo_name.split('.')[:-1])

        # use cached repo
        if os.path.exists(os.path.join(path, repo_dir)) and not force_download:
            self.path = os.path.join(path, repo_dir)
            return

        # clone from github
        setup_env.change_cwd(path)

        while True:
            try:
                check_output_and_logging(['git', 'clone', self.url])
            except:
                logger.info('git clone failed, retrying...')
                continue
            break

        self.path = os.path.join(path, repo_dir)
        setup_env.recover_cwd()

    def get_builder(self):
        if self.path is None:
            raise AttributeError('Download first to start analysis')

        return builder.get_builder(self.path)

    def get_version_list(self):
        if self.version_list:
            return self.version_list

        self.version_list = []

        setup_env.change_cwd(self.path)

        with os.popen('git tag') as f:
            tags = f.readlines()
            for line in tags:
                line = line.replace('\n', '')
                self.version_list.append(line)

        setup_env.recover_cwd()

        return self.version_list

    def switch_to_version(self, version):
        if self.path is None:
            raise AttributeError('Download first to start analysis')

        setup_env.change_cwd(self.path)

        try:
            check_output_and_logging(['git', 'checkout', version])
        except:
            logger.error('Something error when checkout to %s' % version)
