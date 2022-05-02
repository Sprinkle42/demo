import os
import sys
import json
import argparse

import builder
import database
import setup_env
from utils import logger, check_output_and_logging

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--action', default='None', help='do something')
    parser.add_argument('--taskid', default='None', help='taskid')
    parser.add_argument('--depth', default=3, help='max dependency depth')

    args = parser.parse_args()
    args.depth = int(args.depth)
    return args

def dependency(args):
    if args.taskid == 'None':
        logger.error('Taskid is needed for action querydep')
        return

    path = os.path.join('/root/osschain/task', args.taskid)
    if not os.path.exists(path):
        logger.error('Taskid %s does not exist.' % args.taskid)
        return

    # set environment
    setup_env.change_java_default()

    logger.info(os.environ['JAVA_HOME'])

    # create a dict database
    db = database.get_database(database.DB_TYPE_DICT)

    # get builder
    bdr = builder.get_builder(path) 

    # get groupid and version
    metadata = bdr.get_metadata()
    metadata['builder'] = bdr.type
    group_id = metadata['groupId']

    # get dependency
    bdr.parse_dependency(database=db, force_reanalyze=True)
    dependency, ndeps, stats = db.query(group_id, max_depth=args.depth)

    # count multi-level dependencies
    metadata['n_dep'] = ndeps
    metadata['d_dep'] = args.depth
    metadata['n_art'], metadata['level1'], metadata['level2'], metadata['level3'] = stats

    metadata['language'] = bdr.parse_language()

    data = {'metadata': metadata, 'dependency': dependency}

    print(json.dumps(data, indent=4), file=sys.stdout)

################################

action_dict = {
        dependency.__name__: dependency
        }

if __name__ == '__main__':
    args = parse_args()
    action = args.action

    if action not in action_dict:
        logger.error('Unknown action %s' % action)
        exit(1)

    action_dict[action](args)

