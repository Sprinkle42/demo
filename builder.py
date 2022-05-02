import os
import re
import sys
import subprocess
import xml.etree.ElementTree as ET

import setup_env

from utils import logger
from database import construct_db_index, parse_db_index

def parse_programming_language(ext):
    if ext == 'java':
        return 'Java'
    elif ext == 'py':
        return 'Python'
    elif ext == 'c':
        return 'C'
    elif ext == 'cpp' or ext == 'cc':
        return 'C++'
    elif ext == 'sh':
        return 'Bash'
    elif ext == 'cs':
        return 'C#'
    else:
        return 'Others'

class Builder:
    def __init__(self, path):
        self.path = path
        raise NotImplemented('Abstract class cannot be used.')

    def build(self):
        raise NotImplemented('Abstract class cannot be used.')

    def parse_dependency(self, database, force_reanalyze=False):
        raise NotImplemented('Abstract class cannot be used.')

    def parse_language(self):
        res = {}
        tot = 0

        for root, dirs, files in os.walk(self.path):
            for fname in files:
                ext = fname.split('.')[-1]
                lang = parse_programming_language(ext)
                if not lang in res:
                    res[lang] = 0
                res[lang] += 1
                tot += 1

        for lang in res:
            res[lang] /= float(tot) # use explicit case to compatible with python2

        return res

class MavenBuilder(Builder):
    def __init__(self, path):
        self.path = path
        self.type = 'maven'

    def _first_alphabet_pos(self, line):
        s = 0
        for i in line:
            if i.isalpha():
                break
            s += 1
        return s

    def _try_incompatible_java_version(self, loginfo, **kwargs):
        a_pattern = '([^: ]*:[^: ]*:[^: ]*:[^: ]*)'
        pattern = 'Could not find artifact ' + a_pattern

        loginfo = loginfo.strip().split('\n')
        for line in loginfo[::-1]:
            if '[ERROR]' not in line:
                break

            res = re.search(pattern, line)
            if res is None:
                continue

            fullname = res.group(1)
            groupId, artifactId, ext, version = fullname.split(':')
            if groupId.startswith('jdk.'):
                logger.warning("Detect incompatible JDK version")
                logger.warning("Trying to automatically change to %s" % version)
                current_version = setup_env.current_java_env()

                # outdated java not supported, just try 1.8
                if float(version) < 1.65:
                    version = '1.8'
                    logger.warning("version not supported, try %s" % version)

                if current_version == version:
                    logger.error("Already in %s, check other possible reasons!" % current_version)
                    return False
                setup_env.change_java_env(version)

                return True

        return False

    def _try_invalid_protocol_version(self, loginfo, **kwargs):
        # 这个看到log里有invalid protocol类似字样，说明ssl的一些选项不争取，可以临时关闭ssl或者切换加密版本
        # 具体来说，就是给kwargs['cmdline']里append一些参数，下同
        return False

    def _try_ssl_peer_shutdown(self, loginfo, **kwargs):
        # 同上，也是ssl的问题
        return False

    def _try_unresolved_subproject_dependency(self, loginfo, **kwargs):
        # 看到log里有unresolved dependency的，且无法解析的目标就是本工程内的目标（具有相同的groupId），则尝试给cmdline添加compile或install选项
        # 具体原因可以google
        return False

    def _try_invalid_target_release(loginfo, cmdline=cmdline):
        # 这个我有点记不清了，遇到了再补充吧，我记得也是log里出现invalid target release字样
        return False
    
    def build(self):
        pass

    def parse_dependency(self, database, force_reanalyze=False):
        repo_path = self.path

        setup_env.change_java_default()

        os.chdir(repo_path)

        if not os.path.exists('mvnlog.txt') or force_reanalyze:
            os.system('rm mvnlog.txt')

            cmdline = ['dependency:tree']
            while True:
                try:
                    output = subprocess.check_output(['mvn'] + cmdline)
                    break
                except subprocess.CalledProcessError as e:
                    loginfo = e.output.decode()
                    # handleable exceptions
                    if self._try_invalid_protocol_version(loginfo, cmdline=cmdline):
                        continue
                    elif self._try_ssl_peer_shutdown(loginfo, cmdline=cmdline):
                        continue
                    elif self._try_incompatible_java_version(loginfo, cmdline=cmdline):
                        continue
                    elif self._try_unresolved_subproject_dependency(loginfo, cmdline=cmdline):
                        continue
                    elif self._try_invalid_target_release(loginfo, cmdline=cmdline):
                        continue
                    # unknown situations, just raise
                    else:
                        raise e

            with open('mvnlog.txt', 'w') as fout:
                fout.write(output.decode())

        setup_env.recover_cwd()

        with open(os.path.join(repo_path, 'mvnlog.txt'), 'r') as flog:
            status = False
            for line in flog:
                if 'maven-dependency' in line:
                    stack = [None]
                    status = True
                    continue

                if status:
                    if not line.startswith('[INFO]'):
                        continue
                    # remove the '[INFO]'
                    line = line[7:]
                    level = self._first_alphabet_pos(line)

                    # check if pure_name is a valid record, if empty or startswith '---', the record is end
                    # 我有点印象，这里有bug，我用状态机来识别哪些log中对应的部分是合法的依赖树
                    # 这里的规则会不对，如果有遇到错误的，需要修改下状态status 的转移规则，具体遇到的时候修改即可
                    if level >= len(line):
                        status = False
                        continue
                
                    pure_name = line[level:].strip()
                    level //= 3
                    pure_name = pure_name.split(':')

                    scope = ''
                    # 上述bug，报错的地方会在这个if-else里面，原因是pure_name不符合格式，就说明这行其实不是合法的依赖树
                    if level == 0:
                        group_id, artifact, artifact_type, version = pure_name
                    else:
                        # deal with 'noaop' flag
                        if len(pure_name) == 6:
                            group_id, artifact, artifact_type, aop_flag, version, scope = pure_name
                            version = version + '-' + aop_flag
                        else:
                            group_id, artifact, artifact_type, version, scope = pure_name

                    db_index = construct_db_index(group_id, artifact, artifact_type, version, scope)

                    if level + 1 < len(stack):
                        for i in range(level, len(stack)):
                            database.write(stack[i], None) # set a None child to mark this artifact has been analyzed
                        # pop the stack before level
                        stack = stack[:level + 1]
                    stack.append(db_index)
                    parent = stack[-2]
                    database.write(parent, db_index) # dependency: parent->db_index

    def get_metadata(self):
        repo_path = self.path
        version = ""
        groupid = ""

        pom = ET.ElementTree(file=os.path.join(self.path, 'pom.xml'))
        root = pom.getroot()
        for ele in root:
            if 'version' in ele.tag:
                version = ele.text
            if 'groupId' in ele.tag:
                groupid = ele.text

        return {'groupId': groupid, 'version': version}

class GradleBuilder(Builder):
    def __init__(self, path):
        self.path = path
        self.type = 'gradle'

    def _get_level(self, line):
        for i in range(len(line)):
            if line[i].isalpha():
                return i // 5

    def build(self):
        pass

    def parse_dependency(self, database, force_reanalyze=False):
        repo_path = self.path
        artifacts = {}

        setup_env.change_java_default()

        os.system('cp getattr.gradle ' + repo_path)
        os.chdir(repo_path)

        # step1: parse all project names
        if not os.path.exists('gradlelog.txt') or force_reanalyze:
            # before reanalyze, clean cache
            os.system('rm gradlelog.txt')

            output = subprocess.check_output(['./gradlew', '--init-script=./getattr.gradle', 'getProjectAttr']).decode()
            with open('gradlelog.txt', 'w') as fout:
                fout.write(output)

        # step2: make up artifact dict {projectName: [artifact1, artifact2]}
        with open('./gradlelog.txt', 'r') as fin:
            os.system('rm gradledep.txt')

            lines = fin.read()
            lines = lines.split('========\n')[1:-1]
            # for each gradle project
            for i, line in enumerate(lines):
                line = line.split('--------\n')
                projectName = line[0].strip()
                line = line[1:]

                # get all artifacts in the project
                artifacts[projectName] = []
                for artifact in line:
                    groupId, artifactId, fileExt, version = artifact.split('\n')[:4]
                    artifacts[projectName].append(':'.join([artifactId, groupId, fileExt, version]))

                # get dependencies via gradlew api
                output = subprocess.check_output(['./gradlew', '%s:dependencies' % projectName])

                with open('gradledep.txt', 'a') as fout:
                    fout.write(output.decode())

        # step3: construct dependency tree
        stack = [None]
        with open('./gradledep.txt', 'r') as fin:
            dep_tag = [' ', '+', '|', '\\']
            project_name = None
            project_flag = False
            for line in fin:
                if line[0] == '-':
                    project_flag = not project_flag
                    continue

                # when find a new project, clean stack
                if project_flag:
                    project_name = re.search("'.+'", line).group().replace('\'', '')
                    
                    # root project name should be ':'
                    if ':' not in project_name:
                        project_name = ':'

                    stack = [artifacts[project_name]]

                # we find a project, then we parse its dependencies
                if project_name and not project_flag:
                    if line[0] in dep_tag:
                        level = self._get_level(line)
                        artifact_name = line[level * 5:]

                        # broken dependency, just ignore
                        if artifact_name.startswith('unspecified'):
                            continue
                        # depend on sub project
                        elif artifact_name.startswith('project'):
                            subproject = artifact_name.split(' ')[1].strip()

                            # sometimes, subproject will omit ':' in the beginning
                            # correct: 'project :logstash-core'
                            # wrong:   'project logstash-core'
                            # it seems to be a BUG
                            # so we just add ':' before such subproject
                            #
                            # just add ':' doesn't work, sometimes it is ambiguous
                            # for example
                            # 'project api' in 'kafka:storage' dependencies
                            # but in the project, there are ':client:api' and ':storage:api'
                            # so it is not clear what the 'api' is
                            # we just skip it
                            if subproject[0] != ':':
                                continue
                                # subproject = ':' + subproject

                            artifact = artifacts[subproject]
                        # depend on external artifact
                        else:
                            group_id, artifact_id, version = artifact_name.strip().split(' ')[0].split(':')
                            artifact = [':'.join([group_id, artifact_id, 'jar', version])]

                        # var artifact is a list of artifacts
                        # if current element is an externel dependency, artifact list will include a single artifact
                        # if current element is a subproject, artifact list will include all artifacts in this project

                        if len(stack) > level:
                            stack = stack[:level]
                        stack.append(artifact)

                        for parent in stack[-2]:
                            for child in stack[-1]:
                                database.write(parent, child)

        setup_env.recover_cwd()

    def get_metadata(self):
        data = {}

        os.system('cp getattr.gradle ' + self.path)
        os.chdir(self.path)
        output = subprocess.check_output(['./gradlew', '--init-script=./getattr.gradle', 'getMetadata']).decode().split('\n')
        setup_env.recover_cwd()

        group_flag = False
        ver_flag = False
        for line in output:
            if '[GROUP]' in line:
                group_flag = True
                continue

            if group_flag:
                data['groupId'] = line.strip()
                group_flag = False
                continue

            if '[VERSION]' in line:
                ver_flag = True
                continue

            if ver_flag:
                data['version'] = line.strip()
                ver_flag = False
                continue

        return data

class AntBuilder(Builder):
    def __init__(self, path):
        self.path = path
        self.type = 'ant'

    def build(self):
        pass

    def parse_dependency(self, database, force_reanalyze=False):
        pass

    def get_metadata(self):
        pass

def get_builder(path):
    if os.path.exists(os.path.join(path, 'pom.xml')):
        return MavenBuilder(path)
    elif os.path.exists(os.path.join(path, 'gradlew')):
        return GradleBuilder(path)
    elif os.path.exists(os.path.join(path, 'build.xml')):
        return AntBuilder(path)

