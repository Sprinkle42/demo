import os

import repo
import builder
import database

from utils import logger

repo_dir = './repo'
if __name__ == '__main__':
    db = database.get_database(database.DB_TYPE_FS)

    repo = repo.GithubRepository('https://github.com/apache/storm.git')
    repo.download('/root/osschain/repo')

    versions = repo.get_version_list()

    for version in versions:
        ret = repo.switch_to_version(version)
        os.system('git branch | head -1')
        try:
            builder = repo.get_builder()
            logger.info(builder.type)
            builder.parse_dependency(db, force_reanalyze=True)
        except:
            logger.info("Error: Unknown builder for %s:%s" % (repo.path, version))

