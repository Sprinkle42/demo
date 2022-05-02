import os
import pickle

DB_TYPE_UNKNOWN = 0
DB_TYPE_FS = 1
DB_TYPE_MYSQL = 2
DB_TYPE_DICT = 3

CURRENT_DB_TYPE = DB_TYPE_FS

def construct_db_index(group_id, artifact, artifact_type, version, scope):
    return ':'.join([group_id, artifact, artifact_type, version])

def parse_db_index(db_index):
    return db_index.split(':')

def get_database(db_type):
    if db_type == DB_TYPE_FS:
        return FileSystemDatabase()
    elif db_type == DB_TYPE_MYSQL:
        return MySQLDatabase()
    elif db_type == DB_TYPE_DICT:
        return DictDatabase()
    else:
        raise AttributeError("Unknown database type: %d" % db_type)

# Abstract class, should not be used directly
class Database:
    def __init__(self):
        raise NotImplemented('Abstract class DataBase can not be used')

    def write(self, parent, child):
        raise NotImplemented('Abstract class DataBase can not be used')

# File system database
class FileSystemDatabase(Database):
    def __init__(self):
        self.dir = './database'
        if not os.path.exists(self.dir):
            os.makedirs(self.dir)
    
    def _db_fs_entry(self, db_index):
        return os.path.join(self.dir, db_index)

    def _db_fs_create_empty(self, db_index):
        with open(self._db_fs_entry(db_index), 'wb') as db_file:
            pickle.dump({}, db_file, protocol=4)

    def write(self, parent, child):
        # if child is a root node, just skip
        if parent is None:
            return

        # create data file if not exist
        if not os.path.exists(self._db_fs_entry(parent)):
            self._db_fs_create_empty(parent)

        # no child, empty node is enough to mark that 'parent' have been analyzed
        if child is None:
            return

        # read data file, and add the relationship between parent and child
        with open(self._db_fs_entry(parent), 'rb') as db_file:
            dependency_dict = pickle.load(db_file)
        dependency_dict[child] = 0
        with open(self._db_fs_entry(parent), 'wb') as db_file:
            pickle.dump(dependency_dict, db_file, protocol=4)

# Mysql database
class MySQLDatabase(Database):
    def __init__(self):
        pass

    def write(self, parent, child):
        if parent is None:
            pass

        if child is None:
            pass

# Dict database
class DictDatabase(Database):
    def __init__(self):
        self.data = {}
        self.levels = [{}, {}, {}, {}] # level 0-3
        self.unique = {}

    def write(self, parent, child):
        if parent is None:
            return

        if not parent in self.data:
            self.data[parent] = {}

        if child is not None:
            self.data[parent][child] = 0

    def _query(self, group_id, parent, level, max_depth):
        tmp = {}

        if level < max_depth and parent in self.data:
            for child in self.data[parent]:
                tmp[child] = self._query(group_id, child, level + 1, max_depth)

        # do not distinguish level > 3
        if level > 3:
           level = 3

        # artifacts occurs with level > 0 should not be counted as dependency
        if not parent.startswith(group_id) or level == 0:
            if not parent in self.levels[level]:
                self.levels[level][parent] = 0
            self.levels[level][parent] += 1

        # artifacts should not be counted into dependencies
        if level > 0 and not parent.startswith(group_id):
            if not parent in self.unique:
                self.unique[parent] = 0

        return tmp

    def query(self, group_id, max_depth):
        res = {}
        for parent in self.data.keys():
            if parent.startswith(group_id):
                res[parent] = self._query(group_id, parent, 0, max_depth)

        stats = list(map(len, self.levels))
        ndeps = len(self.unique)

        return res, ndeps, stats

